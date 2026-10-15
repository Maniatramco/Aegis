FROM alpine:3.23
RUN apk add --no-cache openssh-server && adduser -D -s /sbin/nologin relay && passwd -d relay && mkdir -p /run/sshd /run/ssh-host /home/relay/.ssh && chown -R relay:relay /home/relay
COPY sshd_config /etc/ssh/sshd_config
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh
EXPOSE 2222
CMD ["/entrypoint.sh"]
