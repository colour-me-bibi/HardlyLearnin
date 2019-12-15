import re
import textract
import glob
import sqlite3
import sys
import os
import pickle
import atexit
import time
from codecs import encode, decode
from model.Chunk import Chunk
from model.Source import Source
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget


def get_chucks(docx_file):
    """Returns a list of chunks of content from a docx file"""

    text = str(textract.process(docx_file)).strip('b\'')
    seq_new_line_counts = {text.count(x): x for x in set(
        re.findall(r'(?:\\n)+', str(text)))}
    splitters = list(sorted(seq_new_line_counts.items()))
    # TODO maybe return list of Chunk objects
    return re.split('|'.join(map(re.escape, [x[1] for x in splitters[:-1]])), text)


def init_db(file_base_name='HardlyLearnin'):
    """Initializes the sqlite db connection as the global variable conn"""

    global conn
    conn = sqlite3.connect(f'{file_base_name}.db')

    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS chunks (
        content TEXT,
        source TEXT
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS imported (
        source TEXT UNIQUE
    )''')

    conn.commit()

    return conn


def insert_chunk(chunk):
    """Insets a chunk into the sqlite db"""

    conn.cursor() \
        .execute('INSERT INTO chunks VALUES (?, ?)', (chunk.content, chunk.source)) \
        .commit()


def insert_import(source):
    """Inserts an import into the sqlite db"""

    conn.cursor() \
        .execute('INSERT INTO imported VALUES (?)', (source,)) \
        .commit()


def search_chunks(string):
    """Returns a the results of a search in the sqlite db of chunks for a given string"""

    return conn.cursor() \
        .execute(f'SELECT * FROM chunks WHERE content LIKE ?', (f'%{string}%',)) \
        .fetchall()


def format_results(list_of_chunks):
    """Returns text formatted for a QTextBrowser"""

    def wrap_in_link(path):
        """Returns a path wraped in an html link tag"""

        return f'<a href={os.path.abspath(path)}>{path}</a>'

    added_links = [(x[0], wrap_in_link(x[1])) for x in list_of_chunks]

    return str(added_links).replace('\\\\n', '\n').replace('\\\\t', '\t')


def load_cache():
    """Returns the cache loaded from the cache.pickle file"""

    with open('serialized/cache.pickle', 'rb') as in_pickle:
        return pickle.load(in_pickle)


def save_cache():
    """Save the cache from the cache global variable as a pickle file"""

    with open('serialized/cache.pickle', 'wb') as out_pickle:
        pickle.dump(cache, out_pickle)
    conn.close()


def text_changed(search_input):
    """
    Updates the text in the results QTextBrowser with formatted results
        from the cache if available, otherwise from the sqlite db
    """

    text = cache[search_input] if search_input in cache.keys() else None

    if text is None:
        text = format_results(search_chunks(search_input))
        cache[search_input] = text

    results.setText(text)

    if text != '[]':
        history.append(search_input)


if __name__ == '__main__':
    docx_files = glob.glob('test_data/**.docx')

    init_db()

    global cache
    cache = load_cache() if os.path.getsize(
        'serialized/cache.pickle') > 0 else dict()

    atexit.register(save_cache)

    for docx_file in docx_files:
        try:
            insert_import(docx_file)
            for chunk in get_chucks(docx_file):
                insert_chunk(Chunk(chunk, docx_file))
        except sqlite3.IntegrityError:
            print(f'Already imported {docx_file}')

    app = QApplication(sys.argv)
    window = QMainWindow()

    uic.loadUi('ui/HardlyLearnin.ui', window)

    window.setWindowTitle('HardlyLearnin')

    global search_bar
    search_bar = window.findChild(QtWidgets.QLineEdit, 'search_bar')

    global results
    results = window.findChild(QtWidgets.QTextBrowser, 'results')

    global history
    history = window.findChild(QtWidgets.QTextBrowser, 'history')

    search_bar.textChanged[str].connect(lambda x: text_changed(x))

    window.show()

    sys.exit(app.exec_())
