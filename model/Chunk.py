class Chunk:
    def __init__(self, content, source):
        self.content = content
        self.source = source

    def __str__(self):
        return f'Chunk (content: {self.content}, source: {self.source})'