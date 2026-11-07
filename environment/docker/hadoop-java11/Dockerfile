ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS hadoop

# Hadoop 3.2.1's Jetty parser rejects the four-part java.version string in
# newer rolling 11-jre images (for example 11.0.32.1). Pin a Java 11 patch
# release whose java.version remains in the format supported by this Hadoop.
FROM eclipse-temurin:11.0.24_8-jre AS java11

FROM hadoop
USER root
COPY --from=java11 /opt/java/openjdk /opt/java11
# Hadoop 3.2.1's ResourceManager web UI still uses javax.activation, which
# was removed from the JDK in Java 11.
COPY javax.activation-api-1.2.0.jar /opt/hadoop-3.2.1/share/hadoop/common/lib/
ENV JAVA_HOME=/opt/java11
ENV HADOOP_MAPRED_HOME=/opt/hadoop-3.2.1
ENV PATH="/opt/java11/bin:${PATH}"
RUN /opt/java11/bin/java -version
