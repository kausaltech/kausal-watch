#!/usr/bin/env python
"""Simple MCP client tool for testing the Kausal Watch MCP server."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx
from dotenv import dotenv_values


def get_token() -> str:
    """Get the MCP client token from .env file."""
    config = dotenv_values('.env')
    token = config.get('MCP_CLIENT_TOKEN')
    if not token:
        print('Error: MCP_CLIENT_TOKEN not found in .env file', file=sys.stderr)
        sys.exit(1)
    return token


def make_request(
    client: httpx.Client,
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int = 1,
    session_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Make a JSON-RPC request to the MCP server."""
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'Authorization': f'Bearer {get_token()}',
    }
    if session_id:
        headers['Mcp-Session-Id'] = session_id

    payload: dict[str, Any] = {
        'jsonrpc': '2.0',
        'method': method,
        'id': request_id,
    }
    if params:
        payload['params'] = params

    response = client.post('/mcp', headers=headers, json=payload)
    response.raise_for_status()

    # Extract session ID from headers
    new_session_id = response.headers.get('mcp-session-id')

    # Parse SSE response
    text = response.text
    for line in text.split('\n'):
        if line.startswith('data: '):
            data = json.loads(line[6:])
            return data, new_session_id or session_id

    raise ValueError(f'No data found in response: {text}')


def initialize(client: httpx.Client) -> str | None:
    """Initialize MCP session and return session ID (if stateful mode is enabled)."""
    result, session_id = make_request(
        client,
        'initialize',
        params={
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'mcp-client-tool', 'version': '1.0'},
        },
    )
    if 'error' in result:
        print(f'Error initializing: {result["error"]}', file=sys.stderr)
        sys.exit(1)

    print(f'Connected to: {result["result"]["serverInfo"]["name"]} v{result["result"]["serverInfo"]["version"]}')
    # Session ID is optional in stateless mode
    # TODO: Re-enable session ID requirement when stateful mode is restored
    return session_id


def list_tools(client: httpx.Client, session_id: str | None) -> list[dict[str, Any]]:
    """List available tools."""
    result, _ = make_request(client, 'tools/list', session_id=session_id, request_id=2)
    if 'error' in result:
        print(f'Error listing tools: {result["error"]}', file=sys.stderr)
        sys.exit(1)
    return result['result']['tools']


def call_tool(
    client: httpx.Client, session_id: str | None, tool_name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Call a tool and return the result."""
    params: dict[str, Any] = {'name': tool_name}
    if arguments:
        params['arguments'] = arguments

    result, _ = make_request(client, 'tools/call', params=params, session_id=session_id, request_id=3)
    if 'error' in result:
        print(f'Error calling tool: {result["error"]}', file=sys.stderr)
        sys.exit(1)
    return result['result']


def describe_tool(tools: list[dict[str, Any]], tool_name: str, raw: bool = False) -> None:
    """Show full details of a specific tool."""
    tool = next((t for t in tools if t['name'] == tool_name), None)
    if not tool:
        print(f"Error: Tool '{tool_name}' not found", file=sys.stderr)
        print(f'Available tools: {", ".join(t["name"] for t in tools)}', file=sys.stderr)
        sys.exit(1)

    if raw:
        print(json.dumps(tool, indent=2))
        return

    print(f'\nTool: {tool["name"]}')
    print(f'Description: {tool.get("description", "No description")}')

    input_schema = tool.get('inputSchema', {})
    if input_schema:
        print('\nInput Schema:')
        properties = input_schema.get('properties', {})
        required = set(input_schema.get('required', []))

        if properties:
            for prop_name, prop_info in properties.items():
                req_marker = ' (required)' if prop_name in required else ''
                prop_type = prop_info.get('type', 'any')
                prop_desc = prop_info.get('description', '')
                print(f'  - {prop_name}: {prop_type}{req_marker}')
                if prop_desc:
                    print(f'      {prop_desc}')
        else:
            print('  (no parameters)')

    output_schema = tool.get('outputSchema')
    if output_schema:
        print('\nOutput Schema:')
        print(json.dumps(output_schema, indent=2))


def print_tools_list(tools: list[dict[str, Any]]) -> None:
    """Print a formatted list of tools."""
    print(f'\nAvailable tools ({len(tools)}):')
    for tool in tools:
        description = tool.get('description', 'No description')
        # Indent continuation lines for multi-line descriptions
        lines = description.split('\n')
        first_line = lines[0]
        print(f'  - {tool["name"]}: {first_line}')
        for line in lines[1:]:
            print(f'      {line}')


def handle_call_result(result: dict[str, Any], raw: bool) -> None:
    """Handle and print the result of a tool call."""
    if raw:
        print(json.dumps(result, indent=2))
        return

    # Show text content
    for content in result.get('content', []):
        if content.get('type') == 'text':
            print(f'\n{content["text"]}')

    # Show structured content if present
    if 'structuredContent' in result:
        print('\nStructured content:')
        print(json.dumps(result['structuredContent'], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description='Test the Kausal Watch MCP server')
    parser.add_argument('--base-url', default='http://localhost:8000', help='Base URL of the server')
    parser.add_argument('--list-tools', action='store_true', help='List available tools')
    parser.add_argument('--describe', metavar='TOOL', help='Show full details of a tool (description, input/output schema)')
    parser.add_argument('--call', metavar='TOOL', help='Call a tool by name')
    parser.add_argument('--args', metavar='JSON', help='JSON arguments for the tool call')
    parser.add_argument('--raw', action='store_true', help='Output raw JSON response')

    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        session_id = initialize(client)

        if args.list_tools:
            tools = list_tools(client, session_id)
            if args.raw:
                print(json.dumps(tools, indent=2))
            else:
                print_tools_list(tools)
        elif args.describe:
            tools = list_tools(client, session_id)
            describe_tool(tools, args.describe, raw=args.raw)
        elif args.call:
            arguments = json.loads(args.args) if args.args else {}
            result = call_tool(client, session_id, args.call, arguments)
            handle_call_result(result, args.raw)
        else:
            # Default: list tools with usage hint
            tools = list_tools(client, session_id)
            print_tools_list(tools)
            print('\nUse --call TOOL to call a tool, e.g.:')
            print(f'  python {sys.argv[0]} --call list_plans')
            print(f'  python {sys.argv[0]} --call hello_world --args \'{{"name": "World"}}\'')


if __name__ == '__main__':
    main()
