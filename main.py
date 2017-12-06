#!/usr/bin/env python3

from gevent import monkey
# need to patch sockets to make requests async
monkey.patch_all(
    socket=True,
    dns=True,
    time=True,
    select=True,
    thread=True,
    os=True,
    ssl=True,
    httplib=False,
    subprocess=False,
    sys=False,
    aggressive=True,
    Event=False,
    builtins=True,
    signal=True)

import click

from zerorobot.robot import Robot


@click.command()
@click.option('--data-repo', '-D', required=True, help='URL of the git repository where to save the data of the zero robot')
@click.option('--template-repo', '-T', multiple=True, help='list of templare repository URL')
@click.option('--listen', '-L', help='listen address', default=':6600')
def main(data_repo, template_repo, listen):
    robot = Robot()
    for url in template_repo:
        robot.add_template_repo(url)
    robot.set_data_repo(data_repo)
    robot.start(listen=listen)

if __name__ == "__main__":
    main()