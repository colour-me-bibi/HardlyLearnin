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
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget

from model.Chunk import Chunk
from model.Source import Source


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        uic.loadUi('ui/HardlyLearnin.ui', self)
        self.setWindowTitle('HardlyLearnin')
        self.show()

        self.debounce = QTimer()
        self.debounce.setInterval(500)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.text_submitted)

        self.search_bar = self.findChild(QtWidgets.QLineEdit, 'search_bar')
        self.search_bar.textChanged[str].connect(self.debounce.start)

        self.history_list = list()
        self.history = self.findChild(QtWidgets.QListWidget, 'history')
        self.history.itemClicked.connect(lambda x: self.search_bar.setText(x.text()))

        self.results = self.findChild(QtWidgets.QTextBrowser, 'results')

        logging.basicConfig(filename='HardlyLearnin.log',
                            level=logging.INFO,
                            format='%(levelname)s %(asctime)s %(message)s')
        self.logger = logging.getLogger()

        self.conn = self.init_db()

        self.cache = self.load_cache()

        for docx_file in glob.glob('import/**.docx'):
            try:
                self.insert_source(Source(docx_file, get_hash_of_file(docx_file)))
                for chunk in get_chucks(docx_file):
                    self.insert_chunk(Chunk(chunk, docx_file))
            except sqlite3.IntegrityError:
                self.logger.info(f'Already imported {docx_file}')

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

    def insert_chunk(self, chunk):
        """Insets a chunk into the sqlite db"""

        self.conn.cursor().execute('INSERT INTO chunks VALUES (?, ?)', (chunk.content, chunk.source))
        self.conn.commit()

    def insert_source(self, source):
        """Inserts an import into the sqlite db"""

        result = self.conn.cursor() \
            .execute('SELECT name FROM sources WHERE name = ? AND file_hash != ?', (source.name, source.file_hash)) \
            .fetchone()
        if result is not None:
            self.remove_old(source.name)

        self.conn.cursor().execute('INSERT INTO sources VALUES (?, ?)', (source.name, source.file_hash))
        self.conn.commit()

    def remove_old(self, name):
        self.conn.cursor().execute('DELETE FROM chunks WHERE source = ?', (name,))
        self.conn.cursor().execute('DELETE FROM sources WHERE name = ?', (name,))
        self.conn.commit()

        for x, y in self.cache.items():
            if y == name:
                del self.cache[x]  # TODO probably can be optimized

    def search_chunks(self, string):
        """Returns a the results of a search in the sqlite db of chunks for a given string"""

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
                text = format_results(self.search_chunks(search_input))
                self.cache[search_input] = text

            if text != '[]':
                self.results.setText(text)
                if search_input not in self.history_list:
                    self.history_list.append(search_input)
                    self.history.addItem(search_input)
            else:
                self.results.setText(f'No results for...\n\t{text}')

    def clean_up_on_exit(self):
        self.save_cache()
        self.conn.close()
        self.logger.info('Saved cache and closed db connection. Exiting...')


def get_chucks(docx_file):
    """Returns a list of chunks of content from a docx file"""

    text = str(textract.process(docx_file)).strip('b\'')
    seq_new_line_counts = {text.count(x): x for x in set(re.findall(r'(?:\\n)+', str(text)))}
    splitters = list(sorted(seq_new_line_counts.items()))
    # TODO maybe return list of Chunk objects
    return re.split('|'.join(map(re.escape, [x[1] for x in splitters[:-1]])), text)


def format_results(list_of_chunks):
    """Returns text formatted for a QTextBrowser"""

    def wrap_in_link(path):
        """Returns a path wraped in an html link tag"""

        return f'<a href={os.path.abspath(path)}>{path}</a>'

    added_links = [(x[0], wrap_in_link(x[1])) for x in list_of_chunks]

    return str(added_links).replace('\\\\n', '\n').replace('\\\\t', '\t')


def get_hash_of_file(file_path):
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
