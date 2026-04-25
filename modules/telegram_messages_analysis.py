import pandas as pd
import spacy
import re
import logging
import contextlib
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from collections import Counter

from configparser import ConfigParser
from typing import Dict, List, Optional, Tuple, cast

from TELOSX.core.base_module import BaseModule
from TELOSX.database.telegram_group_database import TelegramGroupDatabaseManager, TelegramMessageDatabaseManager, TelegramUserDatabaseManager
from TELOSX.models.database.telegram_db_model import TelegramGroupOrmEntity, TelegramMessageOrmEntity, TelegramUserOrmEntity


logger = logging.getLogger('TelegramExplorer')

class TelegramMessagesAnalysis(BaseModule):
    """Analisi del linguggio dei messaggi """
    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict)-> bool:
         """
        Abstract Method for Module Activation Function.

        :return:
        """
         return cast(bool, args['messages_analysys'])
    
    
    async def run (self, config: ConfigParser, args: Dict, data: Dict)-> None:
            "Execute command"
            if not await self.can_activate(config, args, data):
                return
            
            print("messages analysys")
            
            #Load the spaCy NER model
            nlp = spacy.load('en_core_web_sm')

            #Load message on database 
            db_message: List[TelegramMessageOrmEntity] = TelegramMessageDatabaseManager.get_all_messages_from_group(args['group_id'])


            entity_categories = {
                'PERSON': Counter(),
                'ORG': Counter(),
                'GPE': Counter(),
                'DATE': Counter(),
                # You can add more categories here
            }

            for message in db_message:
                text = message.message

                #Check if the text is a string
                if isinstance(text, str):
                    preprocessed_text = preprocess_text(text)

                with contextlib.suppress(Exception):
                    doc = nlp(preprocessed_text)
                    entities = [(ent.text, ent.label_) for ent in doc.ents]
                    for entity, label in entities:
                        if label in entity_categories:
                            entity_categories[label][entity] += 1
            # Export entities to PDF
            export_entities_to_pdf(entity_categories)
            print(f"PDF report created: Collection/{target_username}/entity_tags.pdf")
            
    # Preprocessing function
    def preprocess_text(text):
        if isinstance(text, str):
            text = re.sub(r'http\S+', '', text)  # Remove URLs
            text = re.sub(r'[^a-zA-Z0-9\s]', '', text)  # Remove non-alphanumeric characters
            text = re.sub(r'(?<=\w)[^\w\s]+(?=\w)', ' ',
                        text)  # Replace punctuation between alphanumeric characters with spaces
        return text
    
    def export_entities_to_pdf(entity_categories, filename='entity_tags.pdf'):
        doc = SimpleDocTemplate(f'Collection/{target_username}/{filename}', pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Mapping for replacing 'ORG' with 'ORGANISATION' and 'GPE' with 'LOCATION'
        category_mapping = {'ORG': 'ORGANISATION', 'GPE': 'LOCATION'}

        # Sort entities within each category by count in descending order
        for category, entities in entity_categories.items():
            if entities:
                sorted_entities = sorted(entities.items(), key=lambda x: x[1], reverse=True)
                entity_str = ", ".join([f"{entity} (x{count})" for entity, count in sorted_entities])
                category_display = category_mapping.get(category, category)
                story.extend(
                    (
                        Paragraph(
                            f"<b>{category_display} Entities:</b> {entity_str}",
                            styles["Normal"],
                        ),
                        Paragraph("<br/><br/>", styles["Normal"]),
                    )
                )
        doc.build(story)

    
    
 
