FROM maven:3.10.0-eclipse-temurin-21-noble AS build
WORKDIR /build
COPY business-server/pom.xml ./
COPY business-server/src ./src
COPY contracts/agent-registry-v1.json /contracts/agent-registry-v1.json
COPY contracts/unicode-casefold.json /contracts/unicode-casefold.json
RUN mvn -B -Dmaven.test.skip=true package

FROM eclipse-temurin:21.0.12.1_1-jre-jammy
RUN apt-get update && apt-get install --no-install-recommends -y git curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN mkdir -p /repository-cache /artifacts/java && chown 10001:10001 /repository-cache /artifacts/java
COPY --from=build /build/target/business-server-0.1.0.jar ./business-server.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/business-server.jar"]
