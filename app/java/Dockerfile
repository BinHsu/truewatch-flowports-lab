# Java test app with the Beacon Java agent. scripts/fetch-vendor.sh puts the four JARs into lib/ and checks their SHA-256.
FROM eclipse-temurin:17.0.11_9-jdk@sha256:39fc8112490b67760d2dd3c8d73176f0ed323e99e7a7f09449d44fb8d1b350cc
COPY lib/ /app/lib/
COPY src/ /app/src/
RUN mkdir /app/classes /evidence \
 && javac -d /app/classes -cp /app/lib/tomcat-embed-core-11.0.27.jar:/app/lib/tomcat-annotations-api-11.0.27.jar /app/src/vulnapp/App.java \
 && rm -rf /app/src
WORKDIR /app
EXPOSE 8080
CMD ["java", "-javaagent:/app/lib/beacon-javaagent-1.3.4.jar", "-cp", "/app/classes:/app/lib/tomcat-embed-core-11.0.27.jar:/app/lib/tomcat-annotations-api-11.0.27.jar:/app/lib/h2-2.5.252.jar", "vulnapp.App"]
