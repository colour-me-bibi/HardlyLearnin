import os
import re
import zipfile

from lxml import etree
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from model import Chunk, Emission, Source


class Worker(QObject):

    sig_done = pyqtSignal(Emission)

    def __init__(self, list_of_sources):
        super(Worker, self).__init__()
        self.list_of_sources = list_of_sources

    @pyqtSlot()
    def work(self):
        name_spaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

        for source in self.list_of_sources:

            zip_file = zipfile.ZipFile(source.name)
            xml_content = zip_file.open('word/document.xml')
            root = etree.parse(xml_content).getroot()

            paragraphs = root.findall('.//w:p', name_spaces)

            html_elements = list()

            for x in paragraphs:
                formatted_html = str()

                text_elements = x.findall('.//w:t', name_spaces)

                if len(text_elements) > 0:
                    highlight = x.find('.//w:highlight', name_spaces)
                    underline = x.find('.//w:u', name_spaces)

                    style_attributes = list()

                    if highlight is not None:
                        style_attributes.append('background-color: yellow')

                    tabs = x.findall('.//w:tab', name_spaces)

                    if len(tabs) > 0:
                        style_attributes.append(f'margin-left: {len(tabs) * 40}px')

                    if len(style_attributes) > 0:
                        formatted_html += f'<p style="{"; ".join(style_attributes)}">'
                    else:
                        formatted_html += '<p>'

                    if underline is not None:
                        formatted_html += '<u>'

                    for element in text_elements:
                        formatted_html += element.text

                    if underline is not None:
                        formatted_html += '</u>'

                    formatted_html += '</p>'
                else:
                    formatted_html = '<br/>'

                html_elements.append(formatted_html)

            raw_string = ''.join(html_elements)

            splitters = list(sorted({raw_string.count(x): x for x in set(re.findall(r'(?:<br\/>)+', raw_string))}.items()))
            raw_list = re.split('|'.join(map(re.escape, [x[1] for x in splitters])), raw_string)

            link_tag = f'<div align="right"><p>Source: <a href="{os.path.abspath(source.name)}">{source.name}</a></p></div></div>'

            appended_links = ['<div padding="10px">' + x + link_tag for x in raw_list]

            list_of_chunks = [Chunk(content, source.name) for content in appended_links]
            self.sig_done.emit(Emission(source, list_of_chunks))
