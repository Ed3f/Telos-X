import pandas as pd
import os
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np

from configparser import ConfigParser
from typing import Dict, List, Optional, Tuple, cast
import logging

from telos_x.core.base_module import BaseModule
from telos_x.database.telegram_group_database import TelegramGroupDatabaseManager, TelegramMessageDatabaseManager, TelegramUserDatabaseManager
from telos_x.models.database.telegram_db_model import TelegramGroupOrmEntity, TelegramMessageOrmEntity, TelegramUserOrmEntity

logger = logging.getLogger('TelegramExplorer')

class TelegramGraphGroupInteraction(BaseModule):
    """Disegno del grafico delle interazioni del gruppo"""

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict)-> bool:
        """
        Abstract Method for Module Activation Function.

        :return:
        """
        return cast(bool, args['graph'])
    
    async def run (self, config: ConfigParser, args: Dict, data: Dict)-> None:
        "Execute command"
        if not await self.can_activate(config, args, data):
            logger.debug('\t\tModule is Not Enabled...')
            return
        
        groups: List[TelegramGroupOrmEntity] = TelegramGroupDatabaseManager.get_all_by_phone_number(
            config['CONFIGURATION']['phone_number'])

        if args['group_id'] and args['group_id'] != '*':
            group_ids: List[int] = [int(group_id) for group_id in args['group_id'].split(',')]
            groups = [group for group in groups if group.id in group_ids]
        
        group_id= args['group_id']
        print (group_id)

        #Create Graph 
        g = nx.DiGraph()

        title = ''
        #Add Nodes 
        db_id_from_user: List[TelegramMessageOrmEntity] = TelegramMessageDatabaseManager.get_all_messages_from_group(group_id)

        sender_user= [db_id_user.from_id for db_id_user in db_id_from_user]
        receiver_user = [db_id_user.to_id for db_id_user in db_id_from_user]

        users_of_group = TelegramUserDatabaseManager.get_user_by_id_group(group_id)
        
        for user in users_of_group:
            sender_id = 0
            receiver_id = 0 
            sender_username = ''
            receiver_username = ''
            if (user.id in sender_user):
                sender_id = user.id
                
                sender_username = user.username
                #check is private user 
                if (sender_username is None):
                    sender_username = 'user'

            #check receiver of message is an user or channel
            if (user.id not in receiver_user):
                receiver_id = group_id

                #set username of group
                for group in groups :
                    if (group.id == group_id):
                        receiver_username = group.group_username
                        title=group.title
            else: 
                receiver_id = user.id
            
            #Create formatted label 
            sender_label= f"User_Id: {sender_id}\n Username: {sender_username}"
            receiver_label= f"User_id: {receiver_id}\n Username: {receiver_username}"
            g.add_node(sender_id, label=sender_label)
            g.add_node(receiver_id, label=receiver_label)

        # Add edges (interactions) and count the number of interactions    
        interaction_count={}
        
        for sender,receiver in zip(sender_user, receiver_user):
            if sender not in interaction_count:
                interaction_count[sender] = {}

            if receiver not in interaction_count[sender]:
                interaction_count[sender][receiver] = 0
            
            interaction_count[sender][receiver] += 1
        
            # Add edges with interaction count as labels
            if (sender is not None):
                g.add_edge(sender, receiver, interactions= interaction_count[sender] [receiver])

        plt.figure(figsize=(14,10))

        # Customize the spring layout with better spacing
        pos = nx.spring_layout(g, seed=42, k=0.15, iterations=50)  # Adjust 'k' and 'iterations' as needed

        labels = nx.get_node_attributes(g, 'label')
        interactions = nx.get_edge_attributes(g, 'interactions')
        edge_labels = {(u, v): str(interactions[(u, v)]) for u, v in g.edges}

        # Node and edge styling
        node_size = 300  # Increase node size to accommodate larger labels
        node_color = 'lightblue'
        edge_width = 1
        edge_color = 'gray'
        font_size = 10
        font_color = 'black'

        # Draw nodes, edges, labels, and edge labels
        nx.draw_networkx_nodes(g, pos, node_size=node_size, node_color=node_color)
        nx.draw_networkx_edges(g, pos, width=edge_width, edge_color=edge_color)

        # Calculate the label positions to avoid cutoff
        label_positions = {node: (pos[node][0], pos[node][1] - 0.02) for node in g.nodes()}

        nx.draw_networkx_labels(g, label_positions, labels, font_size=font_size, font_color=font_color, font_weight='bold')

        # Position edge labels to avoid overlap with nodes
        for (u, v), label in edge_labels.items():
            x = (pos[u][0] + pos[v][0]) / 2  # Calculate x-coordinate
            y = (pos[u][1] + pos[v][1]) / 2  # Calculate y-coordinate
            plt.text(x, y, label, size=font_size, color=font_color, ha='center', va='center')

        
        plt.title(f"User Interaction Network for {title}")

        #Save the visualization to a file
        network_viz_path = os.path.join(f"{title}_network_visualization.png")
        plt.savefig(network_viz_path, bbox_inches='tight', pad_inches=0.1, dpi=400)  # Adjust DPI for higher resolution
        print(f"Network visualization saved to: {network_viz_path}")
        
            