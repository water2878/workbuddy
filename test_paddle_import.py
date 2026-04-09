from paddleocr import PaddleOCR
print("PaddleOCR import OK")
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang='ch')
print("PaddleOCR init OK")
