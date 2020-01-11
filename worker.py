import functools
import os
import re
import subprocess
import zipfile
from glob import glob

import cv2
import pdf2image
import pytesseract
from PIL import Image
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from model import Chunk, Emission, Source


class Worker(QObject):

    sig_log = pyqtSignal(str)
    sig_done = pyqtSignal(Emission)
    sig_complete = pyqtSignal()

    def __init__(self, list_of_sources):
        super(Worker, self).__init__()
        self.list_of_sources = list_of_sources

    @pyqtSlot()
    def work(self):

        # TODO multiprocess process imports

        for ext in ('.docx', '.doc'):
            subprocess.run(f'doc2pdf import/*{ext}', shell=True)

        for source in self.list_of_sources:
            pdf_images = pdf2image.convert_from_path(f'{os.path.splitext(source.name)[0]}.pdf', fmt='png')
            first_image = pdf_images[0]
            combined_image = Image.new('RGB', (first_image.width, first_image.height * len(pdf_images)))

            for i, image in enumerate(pdf_images):
                combined_image.paste(image, (0, i * image.height))

            combined_image.save(f'{os.path.splitext(source.name)[0]}.png')

            cv_image = cv2.imread(f'{os.path.splitext(source.name)[0]}.png')

            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (7, 7), 0)
            thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            dilate = cv2.dilate(thresh, kernel, iterations=8)

            # TODO adjust dilation for better sectioning

            cnts = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cnts = cnts[0] if len(cnts) == 2 else cnts[1]

            list_of_chunks = list()

            for i, c in enumerate(cnts):
                x, y, w, h = cv2.boundingRect(c)
                cropped_image = cv_image[y:y + h, x:x + w]

                cropped_image_path = f'output/{os.path.basename(source.name)}-{i}.png'
                cropped_image_text = pytesseract.image_to_string(cropped_image)

                if re.search(r'[a-zA-Z]', cropped_image_text) is not None:
                    cv2.imwrite(cropped_image_path, cropped_image)
                    list_of_chunks.append(Chunk(cropped_image_text, cropped_image_path, source.name))

            emission = Emission(source, list_of_chunks)

            self.sig_log.emit(f'emitting: {emission}')
            self.sig_done.emit(emission)

        self.sig_complete.emit()

        for item in glob('import/*.png'):
            os.remove(item)

        doc_file_list = [path for ext in ('.docx', '.doc') for path in glob(f'import/*{ext}')]

        for item in glob('import/*.pdf'):
            if any([os.path.splitext(item)[0] == os.path.splitext(x)[0] for x in doc_file_list]):
                os.remove(item)
