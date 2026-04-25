"""Discord Notifier."""
from configparser import SectionProxy

from discord_webhook import DiscordEmbed, DiscordWebhook
from telethon.events import NewMessage

from TELOSX.notifier.notifier_base import BaseNotifier


class DiscordNotifier(BaseNotifier):
    """Basic Discord Notifier."""

    def __init__(self) -> None:
        """Initialize Discord Notifier."""
        super().__init__()
        self.url: str = ''
        self.only_rule_matches: bool = False

    def configure(self, url: str, config: SectionProxy) -> None:
        """Configure the Notifier."""
        self.url = url
        self.configure_base(config=config)

        self.only_rule_matches = (
            'only_rule_matches' in config
            and config['only_rule_matches'].lower() == 'true'
        )

    async def run(self, message: NewMessage.Event, **kwargs) -> None:
        """Run Discord Notifier."""
        is_duplicated, duplication_tag = self.check_is_duplicated(message=message.raw_text)
        if is_duplicated:
            return
        rule_id = kwargs.get('rule_id')

        # Se questo notifier deve notificare solo su rule match, esce se non c'è rule_id
        if self.only_rule_matches and not rule_id:
            return

        webhook = DiscordWebhook(
            url=self.url,
            rate_limit_retry=True
        )

        embed = DiscordEmbed(
            title=f'**{message.chat.title}** ({message.chat.id})',
            description=kwargs.get('translation', message.raw_text or '')
        )

        embed.add_embed_field(name="Message ID", value=str(message.id), inline=False)
        embed.add_embed_field(name="Group Name", value=message.chat.title, inline=True)
        embed.add_embed_field(name="Group ID", value=str(message.chat.id), inline=True)
        embed.add_embed_field(name="Message Date", value=str(message.date), inline=False)
        embed.add_embed_field(name="Tag", value=duplication_tag, inline=False)

        if rule_id:
            embed.add_embed_field(name="Rule ID", value=str(rule_id), inline=False)

        webhook.add_embed(embed)
        webhook.execute()