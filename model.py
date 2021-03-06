class Chunk:
    """This is a class representing the database entry of a chunk from a docx file"""

    def __init__(self, text, image, source):
        self.text = text
        self.image = image
        self.source = source

    def __str__(self):
        return f'Chunk (text: {self.text}, image: {self.image}, source: {self.source})'

class Source:
    """This is a class representing the db entry of a docx file source"""

    def __init__(self, name, file_hash):
        self.name = name
        self.file_hash = file_hash

    def __str__(self):
        return f'Source (name: {self.name}, file_hash: {self.file_hash})'

class Emission:
    """This is a class representing an emission from the worker thread"""

    def __init__(self, source, list_of_chunks):
        self.source = source
        self.list_of_chunks = list_of_chunks

    def __str__(self):
        return f'Emission (source={self.source}, list_of_chunks={[str(x) for x in self.list_of_chunks]})'