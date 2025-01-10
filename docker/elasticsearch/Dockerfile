ARG ES_VERSION=8.13.2
FROM openjdk:23-jdk-slim-bookworm AS builder

RUN apt update && apt install -y git
RUN git clone https://github.com/EvidentSolutions/elasticsearch-analysis-raudikko /tmp/raudikko
WORKDIR /tmp/raudikko
ARG ES_VERSION
ENV ES_VERSION=${ES_VERSION}
RUN ./gradlew build -DelasticsearchVersion=$ES_VERSION

FROM bitnami/elasticsearch:${ES_VERSION}
RUN mkdir /tmp/plugin
COPY --from=builder /tmp/raudikko/build/distributions/elasticsearch*.zip /tmp/plugin
RUN for plugin in /tmp/plugin/*.zip ; do elasticsearch-plugin install file://$plugin ; done
RUN mv /opt/bitnami/elasticsearch/plugins/* /opt/bitnami/elasticsearch/plugins.default/
