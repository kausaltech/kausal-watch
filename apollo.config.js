module.exports = {
  client: {
    includes: ["./paths_integration/**/*.graphql"],
    service: {
      name: "PathsClient",
      url:
        (process.env.PATHS_BACKEND_URL || "https://api.paths.kausal.dev") +
        "/v1/graphql/",
    },
  },
};
