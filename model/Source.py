class Source:
    def __init__(self, source, md5_hash):
        self.source = source
        self.md5_hash = md5_hash

    def __str__(self):
        return f'Source (content: {self.source}, source: {self.md5_hash})'