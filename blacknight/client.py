"""
FarmCloud Client
"""
from kazoo.client import KazooClient
from specification import Specification
from time import sleep
import log
import logging
import sys


class Client(object):

    # ZooKeeper paths
    zk_path = '/blacknight'
    spec_znode = zk_path + '/spec.yaml'
    elect_path = zk_path + '/elect'
    lock_path = zk_path + '/lock'
    ensemble_path = zk_path + '/ensemble'
    services_path = zk_path + '/services'
    unused_hosts_path = services_path + '/unused_hosts'
    hosts_path = zk_path + '/hosts'
    args_path = zk_path + '/args'

    def __init__(self, port='2181'):
        log.add_logger(self)
        self.is_leader = False
        self.local_zk = 'localhost' + ':' + str(port)

        # Start the ZK client
        self.client = KazooClient(self.local_zk)
        self.client.start()

        # Load the appliance specification
        spec_file, stat = self.client.get(Client.spec_znode)
        self.spec = Specification(spec_file)

        # Get synchronization info
        self.election = self.client.Election(Client.elect_path)
        self.lock = self.client.Lock(Client.lock_path)

        self.join_election()

    def lead(self):
        self.info('elected leader')
        self.is_leader = True

        self.client.ensure_path(Client.args_path)
        self.client.ensure_path(Client.services_path)

        @self.client.ChildrenWatch(Client.services_path)
        def watch_services():
            with self.lock:
                sleep(2) # FIXME wait for ephemeral nodes to vanish...
                self.info('leader detected change')
                # TODO: reconfigure ZK
                # ensemble = self._client.get_children(event.path)
                # ensemble = reduce(lambda a, b: a + ',' + b, ensemble)
                # self._client.reconfig('', '', ensemble)

                # Query appliance state and remediate if necessary
                services, args = self.query()
                actions = self.spec.diff(services)
                for action in actions:
                    action.run(args)

        while True:
            cmd = raw_input('> ')
            if cmd == 'help':
                print '\thelp  -- this message'
                print '\tfail  -- simulate failover'
                print '\tquery -- print current appliance state'
            elif cmd == 'fail':
                print 'Simulating failover'
                return
            elif cmd == 'query':
                print 'Current appliance state:'
                print self.query()

    def query(self):
        services = {}
        children = self.client.get_children(Client.services_path)
        for role in children:
            role_path = Client.services_path + '/' + role
            services[role] = self.client.get_children(role_path)

        # Get current appliance configuration
        args = {}
        children = self.client.get_children(Client.args_path)
        for arg in children:
            path = Client.args_path + '/' + arg
            value, stat = self.client.get(path)
            args[arg] = value

        return services, args

    ###############
    #   TESTING   #
    ###############

    # Join the election
    def join_election(self):
        self.debug('Joining election')
        self.is_leader = False
        self.election.run(self.lead)
        self.client.stop()

    # Reset the client connection
    def reset(self):
        self.client.start()
        ensemble_znode = self._ensemble_path + '/' + self.local_zk
        self.client.create(ensemble_znode, ephemeral=True, makepath=True)
        self.join_election()

    # Stop the client connection
    def stop(self):
        self.client.stop()


if __name__ == '__main__':
    log.init_logger()
    logging.basicConfig()

    if len(sys.argv) < 2:
        zkc = Client()
    elif len(sys.argv) < 3:
        port = sys.argv[1]
        zkc = Client(port=port)
