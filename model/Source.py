class Source:
    """This is a class representing the db entry of a docx file source"""

    def __init__(self, name, file_hash):
        self.name = name
        self.file_hash = file_hash

    def __str__(self):
        return f'Source (content: {self.name}, source: {self.file_hash})'
