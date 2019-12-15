class Chunk:
    """This is a class representing the database entry of a chunk from a docx file"""

    def __init__(self, content, source):
        self.content = content
        self.source = source

    def __str__(self):
        return f'Chunk (content: {self.content}, source: {self.source})'
