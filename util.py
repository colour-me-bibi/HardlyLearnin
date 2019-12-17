import textract
import hashlib
import os

def format_results(list_of_chunks):  # TODO unfuck
    """Returns text formatted for a QTextBrowser"""

    def wrap_in_link(path):
        """Returns a path wraped in an html link tag"""

        return f'<a href={os.path.abspath(path)}>{path}</a>'

    added_links = [(x[0], wrap_in_link(x[1])) for x in list_of_chunks]

    return str(added_links).replace('\\\\n', '\n').replace('\\\\t', '\t')


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