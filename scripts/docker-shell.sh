#!/bin/bash

project_name=$1
lava="$(dirname $(dirname $(readlink -f $0)))"
cmd="${@:2}"
#Container name (lava32 or lava32debug) comes from config
. `dirname $0`/vars.sh

docker_map_args="-v $tarfiledir:$tarfiledir"
if [[ "$directory" = "$tarfiledir"* ]]; then true; else
  docker_map_args="$docker_map_args -v $directory:$directory"
fi

if ! ( docker images ${container} | grep -q ${container} ); then
    docker build -t ${container} "$(dirname $(dirname $(readlink -f $0)))/docker/debug"
fi

[ "$extradockerargs" = "null" ] && extradockerargs="";

whoami="$(whoami)"
cmd="sudo -u $whoami bash -c -- \"$cmd\""
if [ -z "$2" ] ; then
    cmd="login -f $whoami LANG=en_US.UTF-8 LANGUAGE=en_US LC_ALL=en_US.UTF-8"
fi

set +x
# to run debugger you need --privileged here
docker run --rm -it \
    --privileged \
    -e "HTTP_PROXY=$HTTP_PROXY" \
    -e "HTTPS_PROXY=$HTTPS_PROXY" \
    -e "http_proxy=$http_proxy" \
    -e "https_proxy=$https_proxy" \
    -e "LANG=en_US.UTF-8" \
    -e "LANGUAGE=en_US:en" \
    -e "LC_ALL=en_US.UTF-8" \
    -v /var/run/postgresql:/var/run/postgresql \
    -v /etc/passwd:/etc/passwd:ro \
    -v /etc/group:/etc/group:ro \
    -v /etc/shadow:/etc/shadow:ro \
    -v /etc/gshadow:/etc/gshadow:ro \
    -v "$HOME":"$HOME" \
    --cap-add=SYS_PTRACE \
    $docker_map_args \
    $extradockerargs \
    ${container} sh -c "trap '' PIPE; $cmd"
