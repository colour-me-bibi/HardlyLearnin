import re

import textract
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from model import Chunk, Emission, Source


class Worker(QObject):

    sig_done = pyqtSignal(int, Emission)

    def __init__(self, id: int, list_of_sources: list):
        super(Worker, self).__init__()
        self.id = id
        self.list_of_sources = list_of_sources

    @pyqtSlot()
    def work(self):
        for source in self.list_of_sources:
            text = str(textract.process(source.name)).strip('b\'')
            seq_new_line_counts = {text.count(x): x for x in set(re.findall(r'(?:\\n)+', str(text)))}
            splitters = list(sorted(seq_new_line_counts.items()))
            # TODO maybe return list of Chunk objects
            raw_list = re.split('|'.join(map(re.escape, [x[1] for x in splitters[:-1]])), text)

            list_of_chunks = [Chunk(content, source.name) for content in raw_list]
            self.sig_done.emit(self.id, Emission(source, list_of_chunks))
