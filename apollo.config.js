function getPathsConfig() {
  return {
    includes: ["./src/paths_integration/**/*.graphql"],
    service: {
      name: "PathsClient",
      url:
        (process.env.PATHS_BACKEND_URL || "https://api.paths.kausal.dev") +
        "/v1/graphql/",
    },
  };
}

function getWatchConfig() {
  const fs = require("fs");
  if (!fs.existsSync("./__generated__/schema.graphql")) return null;
  return {
    includes: ["./src/mcp_server/**/*.graphql"],
    service: {
      name: "WatchClient",
      localSchemaFile: "./__generated__/schema.graphql",
    },
  };
}

module.exports = {
  client: getWatchConfig() ?? getPathsConfig(),
};
