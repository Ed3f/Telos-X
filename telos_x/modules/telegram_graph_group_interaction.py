"""NetworkX visualization of Telegram group message interactions."""

import logging
import re
from configparser import ConfigParser
from pathlib import Path
from typing import Dict, cast

import matplotlib
import networkx as nx

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

from telos_x.core.base_module import BaseModule
from telos_x.database.telegram_group_database import (
    TelegramGroupDatabaseManager,
    TelegramMessageDatabaseManager,
    TelegramUserDatabaseManager,
)
from telos_x.models.database.telegram_db_model import TelegramGroupOrmEntity


logger = logging.getLogger(__name__)


class TelegramGraphGroupInteraction(BaseModule):
    """Generate one interaction graph per selected Telegram group."""

    async def can_activate(
        self,
        config: ConfigParser,
        args: Dict,
        data: Dict,
    ) -> bool:
        return cast(bool, args['graph'])

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        if not await self.can_activate(config, args, data):
            return

        groups = TelegramGroupDatabaseManager.get_all_by_phone_number(
            config['CONFIGURATION']['phone_number']
        )
        if args.get('group_id') and args['group_id'] != '*':
            selected = {int(value) for value in args['group_id'].split(',')}
            groups = [group for group in groups if group.id in selected]

        output_dir = Path(config['CONFIGURATION']['data_path']) / 'export' / 'graphs'
        output_dir.mkdir(parents=True, exist_ok=True)
        for group in groups:
            graph = self.build_graph(group)
            output_path = output_dir / self._output_name(group)
            self.draw_graph(graph, group.title, output_path)
            logger.info('Network visualization saved to: %s', output_path)

    @staticmethod
    def build_graph(group: TelegramGroupOrmEntity) -> nx.DiGraph:
        """Build a group graph using the many-to-many membership API."""
        graph = nx.DiGraph()
        group_node = f'group:{group.id}'
        graph.add_node(group_node, label=group.title or str(group.id), kind='group')

        users = TelegramUserDatabaseManager.get_user_by_id_group(group.id)
        user_nodes = {}
        for user in users:
            node = f'user:{user.id}'
            user_nodes[user.id] = node
            display = user.username or user.first_name or f'user_{user.id}'
            graph.add_node(node, label=display, kind='user')

        messages = TelegramMessageDatabaseManager.get_all_messages_from_group(group.id)
        for message in messages:
            if message.from_id is None:
                continue
            source = user_nodes.get(message.from_id, f'user:{message.from_id}')
            if source not in graph:
                graph.add_node(source, label=str(message.from_id), kind='user')
            target = user_nodes.get(message.to_id, group_node)
            previous = graph.get_edge_data(source, target, {}).get('interactions', 0)
            graph.add_edge(source, target, interactions=previous + 1)
        return graph

    @staticmethod
    def draw_graph(graph: nx.DiGraph, title: str, output_path: Path) -> None:
        """Render a graph to PNG, including valid empty-data graphs."""
        figure = plt.figure(figsize=(14, 10))
        try:
            positions = nx.spring_layout(graph, seed=42, k=0.6, iterations=50)
            labels = nx.get_node_attributes(graph, 'label')
            nx.draw_networkx(
                graph,
                positions,
                labels=labels,
                node_size=900,
                node_color='lightblue',
                edge_color='gray',
                font_size=8,
            )
            edge_labels = nx.get_edge_attributes(graph, 'interactions')
            nx.draw_networkx_edge_labels(graph, positions, edge_labels=edge_labels)
            plt.title(f'User Interaction Network for {title}')
            plt.axis('off')
            figure.savefig(output_path, bbox_inches='tight', pad_inches=0.1, dpi=200)
        finally:
            plt.close(figure)

    @staticmethod
    def _output_name(group: TelegramGroupOrmEntity) -> str:
        safe_title = re.sub(r'[^A-Za-z0-9_.-]+', '_', group.title or 'group')
        return f'{safe_title}_{group.id}_network_visualization.png'
