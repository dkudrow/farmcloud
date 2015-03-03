import logging
from kazoo.client import KazooClient, KazooState
from kazoo.protocol.states import EventType, WatchedEvent
from socket import gethostname
import sys


class ZKClient(object):
    """A ZooKeeper client that monitors the state of a Eucalyptus deployment
    for failures.

    This client participates in an ongoing leader election protocol. Each
    physical machine of the Eucalyptus deployment runs one Client. The Client
    roles in are organized as follows:

        * Primary head node -- does not participate in election
        * Secondary head node -- leader (winner of last election)
        * Node controllers -- candidates in current election

    Candidates in the election block until they win an election, at which
    point their _lead() function is executed. The _lead() function carries out
    the responsibilities of the current leader including:

        * monitoring group membership in the deployment, and
        * reconfiguring the ZooKeeper ensemble;
        * monitoring the secondary head node, and
        * ceding the election when replacing a failed primary head node.

    """

    def __init__(self, port='2181', ensemble_path='/ensemble',
                 elect_path='/elect'):
        self._init_logger()
        # self._local_server = gethostname() + ':' + str(port)
        self._is_leader = False
        self._local_server = 'localhost' + ':' + str(port)
        self._ensemble_path = ensemble_path
        self._elect_path = elect_path
        self.debug('Local server: \'%s\'' % self._local_server)
        self.debug('Ensemble znode: \'%s\'' % self._ensemble_path)
        self.debug('Election znode: \'%s\'' % self._elect_path)

        # Start the client
        self._client = KazooClient(self._local_server)
        self._client.start()
        self.debug('Kazoo client started')

        # Add local ZooKeeper server to ensemble
        ensemble_znode = self._ensemble_path + '/' + self._local_server
        self._client.create(ensemble_znode, ephemeral=True, makepath=True)
        self.debug('\'%s\' added to ensemble' % self._local_server)

        self._set_roles()

        # Join the election
        self._election = self._client.Election(self._elect_path)
        self.join_election()

    def _lead(self):
        def watch_ensemble(event):
            # Watchers cannot be unregistered so we must ensure that only
            # the watcher created by the leader is triggered
            # is_connected = self._client.state == KazooState.CONNECTED
            if event.type == EventType.CHILD and self._is_leader:
                ensemble = self._client.get_children(event.path,
                                                     watch=watch_ensemble)
                ensemble = reduce(lambda a, b: a + ',' + b, ensemble)
                self.info('Detected change in ensemble: %s' % ensemble)
                # self._client.reconfig('', '', ensemble)

        self.info('Elected leader')
        self._is_leader = True
        watch_ensemble(WatchedEvent(EventType.CHILD, None, self._ensemble_path))
        while True:
            cmd = raw_input('> ')
            if cmd == 'help':
                print '\thelp  -- this message'
                print '\tfail  -- simulate failover'
                print '\tquery -- print current deployment state'
            elif cmd == 'fail':
                print 'Simulating failover'
                return
            elif cmd == 'query':
                print 'Current deployment state:'
                print self.query()

    def query(self):
        state = {}
        ensemble = self._client.get_children(self._ensemble_path)
        for node in ensemble:
            state[node] = []
            roles = self._client.get(self._ensemble_path + '/' + node)[0]
            for role in roles.split():
                state[node].append(role)
        return state

    def _init_logger(self, level=logging.DEBUG, logfile=''):
        # Formatter
        formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')

        # Handler
        if logfile == '':
            handler = logging.StreamHandler()
        else:
            handler = logging.FileHandler(logfile)
        handler.setFormatter(formatter)

        # Logger
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(level)
        self._logger.addHandler(handler)

        # Shortcuts
        self.debug = self._logger.debug
        self.info = self._logger.info
        self.warn = self._logger.warn
        self.error = self._logger.error
        self.critical = self._logger.critical

    ###############
    #   TESTING   #
    ###############

    def _set_roles(self):
        port = self._local_server[-4:]
        if port == '2181':
            value = 'primary_head'
        elif port == '2182':
            value = 'secondary_head'
        elif port == '2183':
            value = 'nc hadoop hadoop'
        elif port == '2184':
            value = 'nc hadoop hadoop'
        elif port == '2185':
            value = 'nc hadoop hadoop'
        else:
            print 'Bad port!'
            return
        self._client.set(self._ensemble_path + '/' + self._local_server, value)

    # Join the election
    def join_election(self):
        self.debug('Joining election')
        self._is_leader = False
        self._election.run(self._lead)
        self._client.stop()

    # Reset the client connection
    def reset(self):
        self._client.start()
        ensemble_znode = self._ensemble_path + '/' + self._local_server
        self._client.create(ensemble_znode, ephemeral=True, makepath=True)
        self.join_election()

    # Stop the client connection
    def stop(self):
        self._client.stop()


if __name__ == '__main__':
    logging.basicConfig()

    if len(sys.argv) < 2:
        port = '2181'
    else:
        port = sys.argv[1]

    zkc = ZKClient(port=port)
