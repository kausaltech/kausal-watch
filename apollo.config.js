function getPathsConfig() {
  return {
    includes: ["./paths_integration/**/*.graphql"],
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
  if (!fs.existsSync("./schema.graphql")) return null;
  return {
    includes: ["./mcp_server/**/*.graphql"],
    service: {
      name: "WatchClient",
      localSchemaFile: "./schema.graphql",
    },
  };
}

module.exports = {
  client: getWatchConfig() ?? getPathsConfig(),
};
