# End-to-end test: a fresh distro, a sudo-capable user, then tests/e2e/run.sh.
#   docker build -f tests/e2e/Dockerfile --build-arg BASE=debian:12 -t dotfiles-e2e .
#   docker run --rm dotfiles-e2e
ARG BASE=ubuntu:24.04
FROM ${BASE}
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends sudo ca-certificates >/dev/null \
 && useradd --create-home --shell /bin/bash tester \
 && echo 'tester ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/tester \
 && install -d -o tester -g tester /home/tester/dotfiles  # owned by tester, or git refuses it
USER tester
WORKDIR /home/tester/dotfiles
COPY --chown=tester:tester . .
CMD ["tests/e2e/run.sh"]
