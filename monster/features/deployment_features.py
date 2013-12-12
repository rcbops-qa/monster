""" A Deployment Features
"""

import json
import time
import requests

from monster.features.feature import Feature
from monster import util


class Deployment(Feature):
    """ Represents a feature across a deployment
    """

    def __init__(self, deployment, rpcs_feature):
        self.rpcs_feature = rpcs_feature
        self.deployment = deployment

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        pass

    def pre_configure(self):
        pass

    def apply_feature(self):
        pass

    def post_configure(self):
        pass

#############################################################################
############################ OpenStack Features #############################
#############################################################################


class Neutron(Deployment):
    """ Represents a neutron network cluster
    """

    def __init__(self, deployment, rpcs_feature):
        super(Neutron, self).__init__(deployment, rpcs_feature)
        self.environment = util.config['environments'][str(self)][rpcs_feature]
        self.provider = rpcs_feature

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(self.provider,
                                                      self.environment)
        self._fix_nova_environment()
        self._fix_networking_environment()

    def post_configure(self, auto=False):
        """ Runs cluster post configure commands
        """
        if self.deployment.os_name in ['centos', 'rhel']:
            # This is no longer needed. i think
            #self._reboot_cluster()
            pass

        # Grab the config to auto build or not
        auto_build = auto or \
            util.config[str(self)]['auto_build_subnets']
        self._build_subnets(auto_build)

        # Auto Add default icmp and tcp sec rules
        self._add_security_rules()

    def _add_security_rules(self):
        """ Auto adds sec rules for ping and ssh
        """

        icmp_command = ("{0} security-group-rule-create "
                        "--protocol icmp "
                        "--direction ingress "
                        "default").format(self.provider)
        tcp_command = ("{0} security-group-rule-create "
                       "--protocol tcp "
                       "--port-range-min 22 "
                       "--port-range-max 22 "
                       "--direction ingress "
                       "default").format(self.provider)

        controller = next(self.deployment.search_role('controller'))
        print controller
        print icmp_command
        print tcp_command
        #controller.run_cmd(icmp_command)
        #controller.run_cmd(tcp_command)

    def _fix_networking_environment(self):
        iface = util.config[str(self)][self.deployment.os_name][
            'network_bridge_device']
        provider_network = [
            {"label": "ph-{0}".format(iface),
             "bridge": "br-{0}".format(iface),
             "vlans": "1:1000"}]
        env = self.deployment.environment
        ovs = env.override_attributes[self.provider]['ovs']
        ovs['provider_network'] = provider_network
        env.save()

    def _fix_nova_environment(self):
        # When enabling neutron, have to update the env var correctly
        env = self.deployment.environment
        neutron_network = {'provider': self.provider}
        if 'networks' in env.override_attributes['nova']:
            del env.override_attributes['nova']['networks']
            env.override_attributes['nova']['network'] = neutron_network

        # update the vip to correct api name and vip value
        if self.deployment.feature_in("highavailability"):
            api_name = '{0}-api'.format(self.provider)
            api_vip = util.config[str(self)][self.deployment.os_name]['vip']
            env.override_attributes['vips'][api_name] = api_vip
        env.save()

    def _reboot_cluster(self):

        # reboot the deployment
        self.deployment.reboot_deployment()

        # Sleep for 20 seconds to let the deployment reboot
        time.sleep(20)

        # Keep sleeping till the deployment comes back
        # Max at 8 minutes
        sleep_in_minutes = 5
        total_sleep_time = 0
        while not self.deployment.is_online():
            print "## Current Deployment is Offline ##"
            print "## Sleeping for {0} minutes ##".format(
                str(sleep_in_minutes))
            time.sleep(sleep_in_minutes * 60)
            total_sleep_time += sleep_in_minutes
            sleep_in_minutes -= 1

            # if we run out of time to wait, exit
            if sleep_in_minutes == 0:
                error = ("## -- Failed to reboot deployment"
                         "after {0} minutes -- ##".format(total_sleep_time))
                raise Exception(error)

    def _build_subnets(self, auto=False):
        """ Will print out or build the subnets
        """

        util.logger.info("### Beginning of Networking Block ###")

        network_bridge_device = util.config[str(self)][
            self.deployment.os_name]['network_bridge_device']
        controllers = self.deployment.search_role('controller')
        computes = self.deployment.search_role('compute')

        commands = ['ip a f {0}'.format(network_bridge_device),
                    'ovs-vsctl add-port br-{0} {0}'.format(
                        network_bridge_device)]
        command = "; ".join(commands)

        if auto:
            util.logger.info("### Building OVS Bridge and "
                             "Ports on network nodes ###")
            for controller in controllers:
                controller.run_cmd(command)
                for compute in computes:
                    compute.run_cmd(command)
        else:
            util.logger.info("### To build the OVS network bridge "
                             "log onto your controllers and computes"
                             " and run the following command: ###")
            util.logger.info(command)

        commands = ["source openrc admin",
                    "{0} net-create nettest".format(
                        self.rpcs_feature, network_bridge_device),
                    ("{0} subnet-create --name testnet "
                     "--no-gateway nettest 172.0.0.0/8".format(
                         self.rpcs_feature))]
        command = "; ".join(commands)

        if auto:
            util.logger.info("Adding Neutron Network")
            for controller in controllers:
                util.logger.info(
                    "Attempting to setup network on {0}".format(
                        controller.name))

                network_run = controller.run_cmd(command)
                if network_run['success']:
                    util.logger.info("Network setup succedded")
                    break
                else:
                    util.logger.info(
                        "Failed to setup network on {0}".format(
                            controller.name))

            if not network_run['success']:
                util.logger.info("## Failed to setup networks, "
                                 "please check logs ##")
        else:
            util.logger.info("### To Add Neutron Network log onto the active "
                             "controller and run the following commands: ###")
            for command in commands:
                util.logger.info(command)

        util.logger.info("### End of Networking Block ###")


class Swift(Deployment):
    """ Represents a block storage cluster enabled by swift
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(Swift, self).__init__(deployment, rpcs_feature)
        self.environment = util.config['environments'][str(self)][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            str(self), self.environment)
        self._set_keystone_urls()
        self._fix_environment()

    def post_configure(self, auto=False):
        build_rings = auto or bool(util.config['swift']['auto_build_rings'])
        self._build_rings(build_rings)

    def _set_keystone_urls(self):
        """ Gets the controllers ip and sets the url for the env
        accordingly
        """
        proxy_ip = next(
            self.deployment.search_role('proxy')).ipaddress

        env = self.deployment.environment

        proxy_url = \
            "http://{0}:8080/v1/AUTH_%(tenant_id)s".format(proxy_ip)

        for item in env.override_attributes['keystone']:
            if 'url' in item:
                env.override_attributes['keystone'][item] = proxy_url

        env.save()

    def _fix_environment(self):
        """ This is needed to make the environment for swift line up to the
        requirements from rpcs.
        """

        env = self.deployment.environment
        master_key = util.config['swift']['master_env_key']
        keystone = env.override_attributes['keystone']
        swift = env.override_attributes['swift'][master_key]
        swift['keystone'] = keystone

        util.logger.info("Matching environment: {0} to RPCS "
                         "swift requirements".format(env.name))

        env.del_override_attr('keystone')
        env.del_override_attr('swift')
        env.add_override_attr(master_key, swift)

        env.save()

    def _build_rings(self, auto=False):
        """ This will either build the rings or
            print how to build the rings.
            @param auto Whether or not to auto build the rings
            @type auto Boolean
        """

        # Gather all the nodes
        controller = next(self.deployment.search_role('controller'))
        proxy_nodes = list(self.deployment.search_role('proxy'))
        storage_nodes = list(self.deployment.search_role('storage'))

        #####################################################################
        ################## Run chef on the controller node ##################
        #####################################################################

        controller.run()

        #####################################################################
        ####### Run through the storage nodes and set up the disks ##########
        #####################################################################

        # Build Swift Rings
        disk = util.config['swift']['disk']
        label = util.config['swift']['disk_label']
        for storage_node in storage_nodes:
            commands = ["/usr/local/bin/swift-partition.sh {0}".format(disk),
                        "/usr/local/bin/swift-format.sh {0}".format(label),
                        "mkdir -p /srv/node/{0}".format(label),
                        "mount -t xfs -o noatime,nodiratime,logbufs=8 "
                        "/dev/{0} /srv/node/{0}".format(label),
                        "chown -R swift:swift /srv/node"]
            if auto:
                util.logger.info(
                    "## Configuring Disks on Storage Node @ {0} ##".format(
                        storage_node.ipaddress))
                command = "; ".join(commands)
                storage_node.run_cmd(command)
            else:
                util.logger.info("## Info to setup drives for Swift ##")
                util.logger.info(
                    "## Log into root@{0} and run the following commands: "
                    "##".format(storage_node.ipaddress))
                for command in commands:
                    util.logger.info(command)

        ####################################################################
        ## Setup partitions on storage nodes, (must run as swiftops user) ##
        ####################################################################

        num_rings = util.config['swift']['num_rings']
        part_power = util.config['swift']['part_power']
        replicas = util.config['swift']['replicas']
        min_part_hours = util.config['swift']['min_part_hours']
        disk_weight = util.config['swift']['disk_weight']

        commands = ["su swiftops",
                    "swift-ring-builder object.builder create "
                    "{0} {1} {2}".format(part_power,
                                         replicas,
                                         min_part_hours),
                    "swift-ring-builder container.builder create "
                    "{0} {1} {2}".format(part_power,
                                         replicas,
                                         min_part_hours),
                    "swift-ring-builder account.builder create "
                    "{0} {1} {2}".format(part_power,
                                         replicas,
                                         min_part_hours)]

        # Determine how many storage nodes we have and add them
        builders = util.config['swift']['builders']

        for builder in builders:
            name = builder
            port = builders[builder]['port']

            for index, node in enumerate(storage_nodes):

                # if the current index of the node is % num_rings = 0,
                # reset num so we dont add anymore rings past num_rings
                if index % num_rings is 0:
                    num = 0

                # Add the line to command to build the object
                commands.append("swift-ring-builder {0}.builder add "
                                "z{1}-{2}:{3}/{4} {5}".format(name,
                                                              num + 1,
                                                              node.ipaddress,
                                                              port,
                                                              label,
                                                              disk_weight))
                num += 1

        # Finish the command list
        cmd_list = ["swift-ring-builder object.builder rebalance",
                    "swift-ring-builder container.builder rebalance",
                    "swift-ring-builder account.builder rebalance",
                    "sudo cp *.gz /etc/swift",
                    "sudo chown -R swift: /etc/swift"]
        commands.extend(cmd_list)

        if auto:
            util.logger.info(
                "## Setting up swift rings for deployment ##")
            command = "; ".join(commands)
            controller.run_cmd(command)
        else:
            util.logger.info("## Info to manually set up swift rings: ##")
            util.logger.info(
                "## Log into root@{0} and run the following commands: "
                "##".format(controller.ipaddress))
            for command in commands:
                util.logger.info(command)

        #####################################################################
        ############# Time to distribute the ring to all the boxes ##########
        #####################################################################

        command = "/usr/bin/swift-ring-minion-server -f -o"
        for proxy_node in proxy_nodes:
            if auto:
                util.logger.info(
                    "## Pulling swift ring down on proxy node @ {0}: "
                    "##".format(proxy_node.ipaddress))
                proxy_node.run_cmd(command)
            else:
                util.logger.info(
                    "## On node root@{0} run the following command: "
                    "##".format(proxy_node.ipaddress))
                util.logger.info(command)

        for storage_node in storage_nodes:
            if auto:
                util.logger.info(
                    "## Pulling swift ring down on storage node: {0} "
                    "##".format(storage_node.ipaddress))
                storage_node.run_cmd(command)
            else:
                util.logger.info(
                    "## On node root@{0} run the following command: "
                    "##".format(storage_node.ipaddress))
                util.logger.info(command)

        #####################################################################
        ############### Finalize by running chef on controler ###############
        #####################################################################

        if auto:
            util.logger.info("Finalizing install on all nodes")
            for proxy_node in proxy_nodes:
                proxy_node.run()
            for storage_node in storage_nodes:
                storage_node.run()
            controller.run()
        else:
            for proxy_node in proxy_nodes:
                util.logger.info("On node root@{0}, run the following command: "
                                 "chef client".format(proxy_node.ipaddress))
            for storage_node in storage_nodes:
                util.logger.info("On node root@{0}, run the following command: "
                                 "chef client".format(storage_node.ipaddress))
            util.logger.info(
                "On node root@{0} run the following command: chef-client "
                "##".format(controller.ipaddress))

        util.logger.info("## Done setting up swift rings ##")


class Glance(Deployment):
    """ Represents a glance with cloud files backend
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(Glance, self).__init__(deployment, rpcs_feature)
        self.environment = util.config['environments'][str(self)][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            str(self), self.environment)
        if self.rpcs_feature == 'cf':
            self._add_credentials()

    def _add_credentials(self):
        cf_secrets = util.config['secrets']['cloudfiles']
        user = cf_secrets['user']
        password = cf_secrets['password']

        # acquire tenant_id
        data = ('{{"auth": {{"passwordCredentials": {{"username": "{0}", '
                '"password": "{1}"}}}}}}'.format(user, password))
        head = {"content-type": "application/json"}
        auth_address = self.environment['api']['swift_store_auth_address']
        url = "{0}/tokens".format(auth_address)
        response = requests.post(url, data=data, headers=head, verify=False)
        try:
            services = json.loads(response._content)['access'][
                'serviceCatalog']
        except KeyError:
            raise Exception("Unable to authenticate with Endpoint")
        cloudfiles = next(s for s in services if s['type'] == "object-store")
        tenant_id = cloudfiles['endpoints'][0]['tenantId']

        # set api credentials in environment
        api = self.environment['api']
        api['swift_store_user'] = "{0}:{1}".format(tenant_id, user)
        api['swift_store_key'] = password


class Keystone(Deployment):
    """ Represents the keystone feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(Keystone, self).__init__(deployment, rpcs_feature)
        self.environment = util.config['environments'][str(self)][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            str(self), self.environment)


class Nova(Deployment):
    """ Represents the monitoring feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(Nova, self).__init__(deployment, rpcs_feature)
        self.environment = util.config['environments'][str(self)][
            self.deployment.provisioner.short_name()]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            str(self), self.environment)
        bridge_dev = None
        if self.deployment.provisioner.short_name() == 'openstack':
            bridge_dev = 'eth1'
        elif self.deployment.os_name in ['centos', 'rhel']:
            bridge_dev = 'em1'
        if bridge_dev:
            env = self.deployment.environment

            util.logger.info("Setting bridge_dev to {0}".format(bridge_dev))
            env.override_attributes['nova']['networks']['public'][
                'bridge_dev'] = bridge_dev

            self.deployment.environment.save()


class Horizon(Deployment):
    """ Represents the monitoring feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(Horizon, self).__init__(deployment, rpcs_feature)
        self.environment = util.config['environments'][str(self)][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            str(self), self.environment)


class Cinder(Deployment):
    """ Represents the Cinder feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(Cinder, self).__init__(deployment, rpcs_feature)
        self.environment = util.config['environments'][str(self)][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            str(self), self.environment)


#############################################################################
############### Rackspace Private Cloud Software Features ###################
#############################################################################


class RPCS(Deployment):
    """ Represents a Rackspace Private Cloud Software Feature
    """

    def __init__(self, deployment, rpcs_feature, name):
        super(RPCS, self).__init__(deployment, rpcs_feature)
        self.name = name

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        pass


class Monitoring(RPCS):
    """ Represents the monitoring feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(Monitoring, self).__init__(deployment, rpcs_feature,
                                         str(self))
        self.environment = util.config['environments'][self.name][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            str(self), self.environment)


class MySql(RPCS):
    """ Represents the monitoring feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(MySql, self).__init__(deployment, rpcs_feature,
                                    str(self))
        self.environment = util.config['environments'][self.name][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            self.name, self.environment)


class OsOps(RPCS):
    """ Represents the monitoring feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(OsOps, self).__init__(deployment, rpcs_feature,
                                    str(self))
        self.environment = util.config['environments'][self.name][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            self.name, self.environment)


class DeveloperMode(RPCS):
    """ Represents the monitoring feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(DeveloperMode, self).__init__(deployment, rpcs_feature,
                                            'developer_mode')
        self.environment = util.config['environments'][self.name][rpcs_feature]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            self.name, self.environment)


class OsOpsNetworks(RPCS):
    """ Represents the monitoring feature
    """

    def __init__(self, deployment, rpcs_feature='default'):
        super(OsOpsNetworks, self).__init__(deployment, rpcs_feature,
                                            'osops_networks')
        self.environment = util.config['environments'][self.name][
            self.deployment.provisioner.short_name()]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            self.name, self.environment)


class HighAvailability(RPCS):
    """ Represents a highly available cluster
    """

    def __init__(self, deployment, rpcs_feature):
        super(HighAvailability, self).__init__(deployment, rpcs_feature,
                                               'vips')
        self.environment = util.config['environments'][self.name][
            deployment.os_name]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(self.name,
                                                      self.environment)


class OpenLDAP(RPCS):
    """ Represents a keystone with an openldap backend
    """

    def __init__(self, deployment, rpcs_feature):
        super(OpenLDAP, self).__init__(deployment, rpcs_feature,
                                       str(self))
        self.environment = util.config['environments'][self.name]

    def __repr__(self):
        """ Print out current instance
        """
        outl = 'class: ' + self.__class__.__name__
        return outl

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            self.name, self.environment)

        ldap_server = self.deployment.search_role('openldap')
        password = util.config['ldap']['pass']
        ip = ldap_server.ipaddress
        env = self.deployment.environment

        # Override the attrs
        env.override_attributes['keystone']['ldap']['url'] = \
            "ldap://{0}".format(ip)
        env.override_attributes['keystone']['ldap']['password'] = password

        # Save the Environment
        self.node.deployment.environment.save()


class Openssh(RPCS):
    """ Configures ssh
    """

    def __init__(self, deployment, rpcs_feature):
        super(Openssh, self).__init__(deployment, rpcs_feature, str(self))
        self.environment = util.config['environments'][self.name]

    def update_environment(self):
        self.deployment.environment.add_override_attr(
            self.name, self.environment)
