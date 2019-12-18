import atexit
import glob
import hashlib
import logging
import os
import pickle
import re
import sqlite3
import sys

import textract
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget

from model import Chunk, Emission, Source
from worker import Worker

# TODO fix handling of opening external links


class MainWindow(QMainWindow):
    """MainWindow object, manages the UI and handles db calls"""

    def __init__(self):
        """
        Initializes the UI, logger, db connection, and cache
        then processes files in the import directory
        """

        super(MainWindow, self).__init__()

        uic.loadUi('ui/HardlyLearnin.ui', self)
        self.setWindowTitle('HardlyLearnin')
        self.show()

        self.debounce = QTimer()
        self.debounce.setInterval(500)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.text_submitted)

        self.search_bar = self.findChild(QtWidgets.QLineEdit, 'search_bar')
        self.search_bar.textEdited.connect(self.debounce.start)

        self.history_list = list()
        self.history = self.findChild(QtWidgets.QListWidget, 'history')
        self.history.itemClicked.connect(lambda x: self.history_item_selected(x.text()))

        self.results = self.findChild(QtWidgets.QTextBrowser, 'results')

        logging.basicConfig(filename='HardlyLearnin.log',
                            level=logging.INFO,
                            format='%(levelname)s %(asctime)s %(message)s')
        self.logger = logging.getLogger()

        self.conn = self.init_db()

        self.cache = self.load_cache()

        list_of_sources = [Source(x, get_file_hash(x)) for x in glob.glob('import/**.docx')]
        self.logger.info(f'list_of_sources={[str(x) for x in list_of_sources]}')

        list_of_new_sources = list()

        for source in list_of_sources:
            # Remove files with same hash as new ones
            old_file = self.conn.cursor().execute('SELECT name FROM sources WHERE name = ? AND file_hash != ?',
                                                  (source.name, source.file_hash)).fetchone()
            self.logger.info(f'old_file={old_file}')

            if old_file is not None:
                self.logger.info(f'Removing old references to {source}')
                self.remove_old(source)

            # Remove already imported files from list to be imported
            same_file = self.conn.cursor().execute('SELECT name FROM sources WHERE name = ?', (source.name,)).fetchone()
            self.logger.info(f'same_file={same_file}')

            if same_file is None:
                list_of_new_sources.append(source)
            else:
                self.logger.info(f'Skipping already imported {source}')

        self.logger.info(f'list_of_new_sources={[str(x) for x in list_of_new_sources]}')

        if len(list_of_new_sources) > 0:
            # Initialize worker on a new thread
            self.worker = Worker(list_of_new_sources)
            self.thread = QThread()
            self.worker.moveToThread(self.thread)

            # Define behavior of worker
            self.worker.sig_done.connect(self.insert_emission)
            self.thread.started.connect(self.worker.work)
            self.thread.start()

    def init_db(self, file_base_name='HardlyLearnin'):
        """Initializes the sqlite db connection as the global variable conn"""

        conn = sqlite3.connect(f'{file_base_name}.db')

        conn.cursor().execute('''
        CREATE TABLE IF NOT EXISTS chunks (
            content TEXT,
            source TEXT
        )''')

        conn.cursor().execute('''
        CREATE TABLE IF NOT EXISTS sources (
            name TEXT,
            file_hash TEXT UNIQUE
        )''')

        conn.commit()

        return conn

    def load_cache(self, pickle_path='serialized/cache.pickle'):
        """Returns the cache loaded from the cache.pickle file"""

        if not os.path.exists(pickle_path):  # Creates cache.pickle if not exists
            with open(pickle_path, 'wb+'):
                pass

        if os.path.getsize(pickle_path) > 0:  # Returns cache or empty dict if empty
            with open(pickle_path, 'rb') as in_pickle:
                return pickle.load(in_pickle)
        else:
            return dict()

    def save_cache(self, pickle_path='serialized/cache.pickle'):
        """Save the cache from the cache global variable as a pickle file"""

        with open(pickle_path, 'wb') as out_pickle:
            pickle.dump(self.cache, out_pickle)

    @pyqtSlot(Emission)
    def insert_emission(self, emission):
        for chunk in emission.list_of_chunks:
            self.conn.cursor().execute('INSERT INTO chunks VALUES (?, ?)', (chunk.content, chunk.source))
        self.conn.cursor().execute('INSERT INTO sources VALUES (?, ?)', (emission.source.name, emission.source.file_hash))
        self.conn.commit()

    def remove_old(self, source):
        """Removes references of an old file from the cache and db"""

        self.conn.cursor().execute('DELETE FROM chunks WHERE source = ?', (source.name,))
        self.conn.cursor().execute('DELETE FROM sources WHERE name = ?', (source.name,))
        self.conn.commit()

        for k, v in self.cache.items():
            if v == source.name:
                del self.cache[k]  # TODO probably can be optimized

    def search_chunks(self, string):
        """Returns a the results of a db query on the chunks table for the given string"""

        return self.conn.cursor() \
            .execute(f'SELECT * FROM chunks WHERE content LIKE ?', (f'%{string}%',)) \
            .fetchall()

    def text_submitted(self):
        """
        Updates the text in the results QTextBrowser with formatted results
        from the cache if available, otherwise from the sqlite db
        """

        search_input = self.search_bar.text()

        if search_input is not '':
            text = self.cache[search_input] if search_input in self.cache.keys() else None

            if text is None:
                header = '<DOCTYPE! html><html><body>'
                search_result = '<hr>'.join([x for x, y in self.search_chunks(search_input)])
                footer = '</body></html>'

                text = header + search_result + footer

                self.cache[search_input] = text
                self.logger.info(f'Saved {search_input} to cache')
            else:
                self.logger.info(f'Retrieved {search_input} from cache')

            if text != '[]':
                self.results.setHtml(text)
                if search_input not in self.history_list:
                    self.history_list.append(search_input)
                    self.history.addItem(search_input)
            else:
                self.results.setText(f'No results for {text}...')

    def history_item_selected(self, text):
        """Sets the search_bar to the selected text without deboucing results"""

        self.logger.info(f'history_item_selected: {text}')
        self.search_bar.setText(text)
        self.text_submitted()

    def clean_up_on_exit(self):
        """Called on exit. Saves the cache and closes the db connection."""

        self.save_cache()
        self.conn.close()
        self.logger.info('Saved cache and closed db connection. Exiting...')


def get_file_hash(file_path):
    """Returns the sha1 hash of a file"""

    hasher = hashlib.sha1()

    with open(file_path, 'rb') as hash_file:
        block_size = 65536
        buf = hash_file.read(block_size)
        while len(buf) > 0:
            hasher.update(buf)
            buf = hash_file.read(block_size)

    return hasher.hexdigest()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    GUI = MainWindow()

    atexit.register(GUI.clean_up_on_exit)

    sys.exit(app.exec_())
