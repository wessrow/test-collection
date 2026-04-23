#!/usr/bin/python

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r"""
---
module: ntp_enforcer
short_description: Enforce NTP server configuration on a Cisco IOS device
version_added: "1.0.0"
description:
  - Connects to a Cisco IOS device over SSH and ensures the configured NTP
    servers match the desired C(ntp_servers) list.
  - Only pushes configuration commands when the live device state differs from
    the desired state — making the module fully idempotent.
  - Returns which servers were added or removed so results are always visible in
    the Ansible play recap.
options:
  host:
    description:
      - Hostname or IP address of the Cisco IOS device.
    type: str
    required: true
  username:
    description:
      - SSH username.
    type: str
    required: true
  password:
    description:
      - SSH password.
    type: str
    required: true
    no_log: true
  ntp_servers:
    description:
      - The desired list of NTP server IP addresses or hostnames.
      - Servers not in this list that are currently configured will be removed.
      - Servers in this list that are not yet configured will be added.
    type: list
    elements: str
    required: true
  port:
    description:
      - SSH port.
    type: int
    default: 22
author:
  - Webinar Example
"""

EXAMPLES = r"""
- name: Enforce NTP servers
  ios_ntp_servers:
    host: "{{ inventory_hostname }}"
    username: "{{ ansible_user }}"
    password: "{{ ansible_password }}"
    ntp_servers:
      - 216.239.35.0
      - 216.239.35.4
  register: ntp_result

- name: Show what changed
  ansible.builtin.debug:
    var: ntp_result
  when: ntp_result.changed
"""

RETURN = r"""
changed:
  description: Whether any NTP configuration was pushed to the device.
  type: bool
  returned: always
added_servers:
  description: NTP servers that were added during this run.
  type: list
  elements: str
  returned: always
removed_servers:
  description: NTP servers that were removed during this run.
  type: list
  elements: str
  returned: always
current_servers:
  description: NTP servers configured on the device after this run completes.
  type: list
  elements: str
  returned: always
"""


def _get_current_ntp_servers(connection) -> list[str]:
    output = connection.send_command("show running-config | include ntp server")
    servers: list[str] = []

    for line in output.splitlines():
        parts = line.strip().split()
        # "ntp server <address>" — skip vrf lines for simplicity
        if len(parts) >= 3 and parts[0] == "ntp" and parts[1] == "server":
            servers.append(parts[2])

    return servers


def _push_ntp_changes(connection, to_add: list[str], to_remove: list[str]) -> None:
    commands: list[str] = []

    for server in to_remove:
        commands.append(f"no ntp server {server}")

    for server in to_add:
        commands.append(f"ntp server {server}")

    if commands:
        connection.send_config_set(commands)


def run_module() -> None:
    module = AnsibleModule(
        argument_spec={
            "host": {"type": "str", "required": True},
            "username": {"type": "str", "required": True},
            "password": {"type": "str", "required": True, "no_log": True},
            "ntp_servers": {"type": "list", "elements": "str", "required": True},
            "port": {"type": "int", "default": 22},
        },
        supports_check_mode=True,
    )

    try:
        from netmiko import ConnectHandler
    except ImportError:
        module.fail_json(msg="netmiko is required: pip install netmiko")
        return

    host = module.params["host"]
    username = module.params["username"]
    password = module.params["password"]
    port = module.params["port"]
    desired_servers: list[str] = module.params["ntp_servers"]

    device = {
        "device_type": "cisco_ios",
        "host": host,
        "username": username,
        "password": password,
        "port": port,
    }

    try:
        connection = ConnectHandler(**device)
    except Exception as exc:
        module.fail_json(msg=f"SSH connection failed to {host}: {exc}")
        return

    try:
        current_servers = _get_current_ntp_servers(connection)

        desired_set = set(desired_servers)
        current_set = set(current_servers)

        to_add = sorted(desired_set - current_set)
        to_remove = sorted(current_set - desired_set)

        if not to_add and not to_remove:
            module.exit_json(
                changed=False,
                added_servers=[],
                removed_servers=[],
                current_servers=sorted(current_set),
            )
            return

        if not module.check_mode:
            _push_ntp_changes(connection, to_add, to_remove)

        final_servers = sorted((current_set - set(to_remove)) | set(to_add))

        module.exit_json(
            changed=True,
            added_servers=to_add,
            removed_servers=to_remove,
            current_servers=final_servers,
        )

    finally:
        connection.disconnect()


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
