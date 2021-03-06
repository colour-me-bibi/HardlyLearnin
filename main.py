import atexit
import functools
import hashlib
import logging
import os
import pickle
import re
import sqlite3
import sys
from glob import glob

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget
from yattag import Doc

from model import Chunk, Emission, Source
from worker import Worker


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
        self.search_bar.textEdited.connect(lambda search: self.search_edited(search.strip()))

        self.history_list = list()
        self.history = self.findChild(QtWidgets.QListWidget, 'history')
        self.history.itemClicked.connect(lambda item: self.history_item_selected(item.text()))

        self.results = self.findChild(QtWidgets.QTextBrowser, 'results')
        self.results.anchorClicked.connect(self.open_external_link)

        logging.basicConfig(filename='HardlyLearnin.log',
                            level=logging.INFO,
                            format='%(levelname)s %(asctime)s %(message)s')
        self.logger = logging.getLogger()

        self.conn = self.init_db()

        self.cache = self.load_cache()

        self.imports_complete = False

        self.statusBar.showMessage('Processing imports...')

        list_of_sources = [Source(path, get_file_hash(path))
                           for ext in ('.docx', '.doc', '.pdf') for path in glob(f'import/*{ext}')]

        self.logger.info(f'list_of_sources={[str(x) for x in list_of_sources]}')

        list_of_new_sources = list()

        for source in list_of_sources:
            # Remove files with same hash as new ones
            old_file = self.conn.cursor().execute('SELECT name FROM sources WHERE name = ? AND file_hash != ?',
                                                  (source.name, source.file_hash)).fetchone()
            if old_file is not None:
                self.logger.info(f'Removing old references to {source}')
                self.remove_old(source)

            # Remove already imported files from list to be imported
            same_file = self.conn.cursor().execute('SELECT name FROM sources WHERE name = ?', (source.name,)).fetchone()
            if same_file is None:
                list_of_new_sources.append(source)
            else:
                self.logger.info(f'Skipping already imported {source}')

        self.logger.info(f'list_of_new_sources={[str(x) for x in list_of_new_sources]}')

        if list_of_new_sources:
            # Initialize worker on a new thread
            self.worker = Worker(list_of_new_sources)
            self.thread = QThread()
            self.worker.moveToThread(self.thread)

            # Define behavior of worker
            self.worker.sig_log.connect(lambda msg: self.logger.info(msg))
            self.worker.sig_done.connect(self.insert_emission)
            self.worker.sig_complete.connect(self.imports_completed)
            self.thread.started.connect(self.worker.work)
            self.thread.start()
        else:
            self.imports_completed()

    def init_db(self, file_base_name='HardlyLearnin'):
        """Initializes the db connection as the global variable conn"""

        conn = sqlite3.connect(f'{file_base_name}.db')

        conn.cursor().execute('''
        CREATE TABLE IF NOT EXISTS chunks (
            text TEXT,
            image TEXT,
            source TEXT
        )''')

        conn.cursor().execute('''
        CREATE TABLE IF NOT EXISTS sources (
            name TEXT,
            file_hash TEXT UNIQUE
        )''')

        conn.commit()

        self.logger.info('Initialized the db connection')

        return conn

    def load_cache(self, pickle_path='serialized/cache.pickle'):
        """Returns the cache loaded from the cache.pickle file"""

        if not os.path.exists(pickle_path):  # Creates cache.pickle if not exists
            self.logger.info(f'Creating: {pickle_path}')
            with open(pickle_path, 'wb+'):
                pass

        if os.path.getsize(pickle_path):  # Returns cache or empty dict if empty
            self.logger.info(f'Loading in {pickle_path} as saved cache')
            with open(pickle_path, 'rb') as in_pickle:
                return pickle.load(in_pickle)
        else:
            self.logger.info('Initializing the cache with an empty dict')
            return dict()

    def save_cache(self, pickle_path='serialized/cache.pickle'):
        """Saves the cache from the cache global variable as a pickle file"""

        with open(pickle_path, 'wb') as out_pickle:
            pickle.dump(self.cache, out_pickle)

    @pyqtSlot(Emission)
    def insert_emission(self, emission):
        """Inserts emissions from the worker into the db"""

        for chunk in emission.list_of_chunks:
            self.conn.cursor().execute('INSERT INTO chunks VALUES (?, ?, ?)', (chunk.text, chunk.image, chunk.source))
        self.conn.cursor().execute('INSERT INTO sources VALUES (?, ?)', (emission.source.name, emission.source.file_hash))
        self.conn.commit()

    @pyqtSlot()
    def imports_completed(self):
        """Sets imports_complete to True to enable caching and hides the status bar"""

        self.imports_complete = True
        self.statusBar.hide()

    def remove_old(self, source):
        """Removes references of an old file from the cache, db, and generated images"""

        self.logger.info(f'Removing old source: {source}')

        for x in self.conn.cursor().execute('SELECT image FROM chunks WHERE source = ?', (source.name,)) \
                                   .fetchall():
            os.remove(x[0])

        self.conn.cursor().execute('DELETE FROM chunks WHERE source = ?', (source.name,))
        self.conn.cursor().execute('DELETE FROM sources WHERE name = ?', (source.name,))
        self.conn.commit()

        self.cache = {k: v for k, v in self.cache.items() if v != source.name}

    def search_chunks(self, string):
        """Returns a the results of a db query on the chunks table for the given string"""

        return self.conn.cursor().execute(f'SELECT * FROM chunks WHERE text LIKE ?', (f'%{string}%',)) \
                                 .fetchall()

    def search_edited(self, text):
        if text:
            self.debounce.text = text
            self.debounce.start()
        else:
            self.debounce.stop()
            self.results.setText('')

    def text_submitted(self):
        """
        Updates the text in the results QTextBrowser with formatted results
        from the cache if available, otherwise from the db
        """

        display_text = f'No results for {self.debounce.text}...'

        if self.imports_complete and self.debounce.text in self.cache.keys():
            display_text = self.cache[self.debounce.text]
            self.logger.info(f'Retrieved "{self.debounce.text}" from cache')
        else:
            results = self.search_chunks(self.debounce.text)

            if results:
                doc, tag, text = Doc().tagtext()

                with tag('html'):
                    with tag('body'):
                        for i, (_, image, source) in enumerate(results):
                            with tag('div'):
                                with tag('img', src=image):
                                    pass
                            with tag('div'):
                                with tag('a', href=source):
                                    text(source)

                            if i < len(results) - 1:
                                with tag('hr'):
                                    pass

                display_text = doc.getvalue()

                if self.imports_complete:
                    self.cache[self.debounce.text] = display_text
                    self.logger.info(f'Saved "{self.debounce.text}" to cache')

        self.results.setHtml(display_text)

        if self.debounce.text not in self.history_list:
            self.history_list.append(self.debounce.text)
            self.history.addItem(self.debounce.text)

    def history_item_selected(self, text):
        """Sets the search_bar to the selected text without deboucing results"""

        self.logger.info(f'history_item_selected: {text}')
        self.search_bar.setText(text)
        self.text_submitted()

    def open_external_link(self, qurl):
        """Opens sources clicked from the UI using the default program"""

        self.logger.info(f'Opening extrenal link: {str(qurl)}')
        QDesktopServices.openUrl(qurl)

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
        buffer = hash_file.read(block_size)
        while buffer:
            hasher.update(buffer)
            buffer = hash_file.read(block_size)

    return hasher.hexdigest()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    GUI = MainWindow()

    atexit.register(GUI.clean_up_on_exit)

    sys.exit(app.exec_())
