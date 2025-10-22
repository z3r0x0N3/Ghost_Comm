
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.node.node import Node

class ProxyChain:
    """Manages the chain of proxy nodes."""

    def __init__(self, node_configs: dict, node_order: list):
        """Initializes the ProxyChain with node configurations and order."""
        self.nodes = []
        for node_id in node_order:
            config = node_configs[node_id]
            self.nodes.append(Node(node_id, config['keyword'], config['hashing_algorithm']))

    def process_data(self, data: bytes) -> bytes:
        """Processes data through the proxy chain."""
        processed_data = data
        for node in self.nodes:
            processed_data = node.process_data(processed_data)
        return processed_data

    def get_node_configs(self) -> dict:
        """Returns the current configuration of all nodes in the chain."""
        configs = {}
        for node in self.nodes:
            configs[node.node_id] = {
                'keyword': node.keyword,
                'hashing_algorithm': node.hashing_algorithm
            }
        return configs

    def update_node_configs(self, new_node_configs: dict):
        """Updates the configuration of nodes in the chain."""
        for node in self.nodes:
            if node.node_id in new_node_configs:
                config = new_node_configs[node.node_id]
                node.set_new_config(config['keyword'], config['hashing_algorithm'])
