import re
import textract
import glob
import sqlite3
import sys
from codecs import decode
from model.Chunk import Chunk
from model.Source import Source
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget

# Return list of chunks of content from a docx file
def get_chucks(docx_file):
    text = str(textract.process(docx_file)).strip('b\'')
    seq_new_line_counts = {text.count(x): x for x in set(re.findall(r'(?:\\n)+', str(text)))}
    splitters = list(sorted(seq_new_line_counts.items()))
    # TODO maybe return list of Chunk objects
    return re.split('|'.join(map(re.escape, [x[1] for x in splitters[:-1]])), text)


def init_db(file_base_name='HardlyLearnin'):
    with sqlite3.connect(f'{file_base_name}.db') as conn:
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

def insert_chunk(chunk, conn):
    c = conn.cursor()
    c.execute('INSERT INTO chunks VALUES (?, ?)', (chunk.content, chunk.source))
    conn.commit()

def insert_import(source, conn):
    c = conn.cursor()
    c.execute('INSERT INTO imported VALUES (?)', (source,))
    conn.commit()

def search_chunks(string, conn):
    c = conn.cursor()
    c.execute(f'SELECT * FROM chunks WHERE content LIKE ?', (f'%{string}%',))
    return c.fetchall()

def init_app():
    app = QApplication(sys.argv)
    window = QMainWindow()

    uic.loadUi('ui/HardlyLearnin.ui', window)

    window.setWindowTitle('HardlyLearnin')

    window.show()

    sys.exit(app.exec_())

    return (app, window)

if __name__ == '__main__':
    folder = 'test_data/'
    docx_files = glob.glob(f'{folder}**.docx')

    conn = init_db()

    for docx_file in docx_files:
        try:
            insert_import(docx_file, conn)
            for chunk in get_chucks(docx_file):
                insert_chunk(Chunk(chunk, docx_file), conn)
        except sqlite3.IntegrityError:
            print(f'Already imported {docx_file}')

    search_chunks('dog', conn)

    app, window = init_app()

