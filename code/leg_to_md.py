import os
import argparse
from glob import glob
from tqdm import tqdm
import pymupdf


def get_struck_word_rects(page: pymupdf.Page, height_threshold: float = 1.5) -> set[pymupdf.Rect]:
    """
    Identifies the bounding boxes of words that intersect with potential
    strikethrough drawings (thin, black, filled rectangles).

    Args:
        page: The pymupdf.Page object to analyze.
        height_threshold: Max height for a drawing rect to be considered a strike line.

    Returns:
        A set containing the pymupdf.Rect objects of words identified as struck through.
    """
    strikethrough_line_rects = []
    drawings = page.get_drawings()

    # 1. Filter drawings for potential strikethrough lines
    for drawing in drawings:
        if drawing.get("type") == "f" and drawing.get("fill") == (0.0, 0.0, 0.0):
            for item in drawing.get("items", []):
                if item[0] == "re":
                    rect = pymupdf.Rect(item[1])
                    if 0 < rect.height < height_threshold and rect.width > rect.height * 2: # Check aspect ratio
                        strikethrough_line_rects.append(rect)

    # 2. Get words and their bounding boxes
    words = page.get_text("words")  # List of (x0, y0, x1, y1, word, ...)

    struck_word_bounding_boxes = set()

    # 3. Check for intersections
    for word_data in words:
        word_rect = pymupdf.Rect(word_data[:4])
        word_text = word_data[4]

        if word_rect.is_empty or not word_text.strip():
            continue

        for strike_rect in strikethrough_line_rects:
            intersect_rect = word_rect & strike_rect
            if not intersect_rect.is_empty:
                 # Check vertical alignment and horizontal overlap
                 word_v_center = word_rect.y0 + word_rect.height / 2
                 strike_v_center = strike_rect.y0 + strike_rect.height / 2
                 if (abs(word_v_center - strike_v_center) < (word_rect.height / 4)) and \
                    (intersect_rect.width > word_rect.width * 0.5 or intersect_rect.width > 5):
                     struck_word_bounding_boxes.add(word_rect)
                     break # Word is struck, no need to check other lines

    return struck_word_bounding_boxes

# --- Main Conversion Function ---
def pdf_page_to_markdown(page: pymupdf.Page, include_struck: bool = True) -> str:
    """
    Converts a PDF page to Markdown text, handling strikethroughs.

    Args:
        page: The pymupdf.Page object to convert.
        include_struck: If True, include struck text wrapped in '~~'.
                        If False, omit struck text.

    Returns:
        A string containing the Markdown representation of the page.
    """
    struck_rects = get_struck_word_rects(page)
    words = page.get_text("words") # (x0, y0, x1, y1, word, block_no, line_no, word_no)

    if not words:
        return ""

    # Sort words primarily by vertical position (y0), then horizontal (x0)
    # This helps approximate the reading order
    words.sort(key=lambda w: (w[1], w[0]))

    markdown_output = []
    current_line = ""
    last_y0 = words[0][1] # Y-coordinate of the first word
    last_x1 = words[0][0] # X-coordinate to track horizontal spacing

    # Define a threshold for detecting line breaks (adjust as needed)
    # A bit more than typical line spacing
    line_break_threshold = 10

    for i, word_data in enumerate(words):
        x0, y0, x1, y1, word_text, _, _, _ = word_data
        word_rect = pymupdf.Rect(x0, y0, x1, y1)

        # Check for line break based on vertical distance
        if y0 > last_y0 + line_break_threshold:
            markdown_output.append(current_line.strip())
            current_line = ""
            # Add extra newline for larger gaps (potential paragraph break)
            if y0 > last_y0 + line_break_threshold * 2:
                 markdown_output.append("") # Add blank line
            last_x1 = x0 # Reset horizontal position for new line

        # Add space if it's not the start of a line and there's a gap
        if current_line and x0 > last_x1 + 2: # Add space if gap > 2 points
             current_line += " "

        is_struck = word_rect in struck_rects

        if is_struck:
            if include_struck:
                current_line += f"~~{word_text}~~"
            else:
                # Omit the word - effectively adds nothing to current_line
                pass
        else:
            current_line += word_text

        last_y0 = y0
        last_x1 = x1 # Update the end position of the last added word/strikeout

        # Handle the last word/line
        if i == len(words) - 1:
            markdown_output.append(current_line.strip())


    return "\n".join(markdown_output)


def pdf_text(pdf_file):
    page_texts = list()
    doc = pymupdf.open(pdf_file) # open a document
    for index, page in enumerate(doc):
        page_text = f'PAGE {index}\n{pdf_page_to_markdown(page)}'
        page_texts.append(page_text)
    return "\n\n".join(page_texts)


def main(session_year):
    input_dir = os.path.abspath(f'data/{session_year}rs/pdf')
    output_dir = os.path.abspath(f'data/{session_year}rs/md')
    os.makedirs(output_dir, exist_ok=True)
    pdf_wildcard = os.path.join(input_dir, '*.pdf')
    pdf_files = glob(pdf_wildcard)
    for pdf_file in tqdm(pdf_files):
        file_basename = os.path.basename(pdf_file)
        file_name, _ = os.path.splitext(file_basename)
        destination_basename = '{}.md'.format(file_name)
        destination_file_path = os.path.join(output_dir, destination_basename)
        if not os.path.exists(destination_file_path):
            full_text = pdf_text(pdf_file)
            with open(destination_file_path, 'w', encoding='utf-8') as destination_file:
                destination_file.write(full_text)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse Maryland legislation into markdown.')
    parser.add_argument('session_year', type=int, help='The regular session year')
    args = parser.parse_args()

    main(args.session_year)