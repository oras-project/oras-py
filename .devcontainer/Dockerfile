FROM ghcr.io/oras-project/registry:latest

LABEL maintainer="Vanessasaurus <@vsoch>"

RUN apk update && apk add python3 py3-pip git make apache2-utils bash && \
    pip install --upgrade pip setuptools

ENV registry_host=localhost
ENV registry_port=5000
ENV with_auth=true
ENV REGISTRY_AUTH: "{htpasswd: {realm: localhost, path: /etc/docker/registry/auth.htpasswd}}"
ENV REGISTRY_STORAGE_DELETE_ENABLED="true"
RUN htpasswd -cB -b auth.htpasswd myuser mypass && \
   cp auth.htpasswd /etc/docker/registry/auth.htpasswd && \
   registry serve /etc/docker/registry/config.yml & sleep 5 && \
   echo $PWD && ls $PWD

# Match the default user id for a single system so we aren't root
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000
ENV USERNAME=${USERNAME}
ENV USER_UID=${USER_UID}
ENV USER_GID=${USER_GID}
ENV GO_VERSION=1.21.9


# Add the group and user that match our ids
RUN addgroup -S ${USERNAME} && adduser -S ${USERNAME} -G ${USERNAME} && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers

USER $USERNAME
#     make install
#     make test
