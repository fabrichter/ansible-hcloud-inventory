#!/usr/bin/env python3
import sys
import time

from hcloud import Client
import os
from configparser import ConfigParser
import json


def read_config() -> ConfigParser:
    inventory_script_dir, _ = os.path.split(__file__)
    config_file = os.path.join(inventory_script_dir, 'hcloud.ini')
    config = ConfigParser()
    config.read(config_file)

    if not config.has_section('hcloud'):
        raise ValueError("Configuration with hcloud section required")

    if 'token' not in config['hcloud']:
        raise ValueError("Configuration with token in hcloud section required")

    return config


def clean_name(name):
    # return name.replace('-', '_')
    return name


def hostvars(server):
    s = server.data_model
    return (clean_name(s.name), {
        'ansible_host': s.public_net.ipv4.ip,
        'hcloud_server_type': s.server_type.data_model.name,
        'hcloud_data_center': s.datacenter.data_model.name,
        'hcloud_location': s.datacenter.data_model.location.data_model.name
    })


def matches(selectors, server):
    """
    :param selectors: section from configuration file, with label-value pairs
    :param server: BoundServer from hcloud API
    :return: if a server satisfies set of criteria as specified in a configuration section
    """
    labels = server.data_model.labels.items()
    # get diff in set of items
    diff = selectors ^ labels
    # any difference must not be in specified criteria, i.e. only additional labels for server are ok
    return not any([key in selectors for key in diff])


def main():
    config = read_config()
    token = config['hcloud']['token']

    client = Client(token)
    all_servers = client.servers.get_all()
    filters = []
    if config.has_section('filters'):
        filters = config.items('filters')

    servers = []
    for server in all_servers:
        if matches(filters, server):
            servers.append(server)

    groups_prefix = 'groups:'
    configured_groups = [section for section in config.sections() if section.startswith(groups_prefix)]
    group_filters = {group_section[len(groups_prefix):]: config.items(group_section)
                     for group_section in configured_groups}

    server_info = dict([hostvars(server) for server in servers])

    ungrouped = set(server_info.keys())

    groups = {}
    for group, selectors in group_filters.items():
        groups[group] = []
        for server in servers:
            if matches(selectors, server):
                name = clean_name(server.data_model.name)
                groups[group].append(name)
                ungrouped.discard(name)

    inventory = {
        '_meta': {
            'hostvars': server_info
        },
        "all": {
            "children": list(groups.keys()) + ["ungrouped"]
        },
        "ungrouped": {
            "hosts": list(server_info.keys())
        }
    }
    for group, hosts in groups.items():
        inventory[group] = {'hosts': hosts}

    json.dump(inventory, sys.stdout)


if __name__ == '__main__':
    main()
