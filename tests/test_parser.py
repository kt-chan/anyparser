import pytest
from app.utils.markdown_parser import MarkdownParser

def test_markdown_parser_structure():
    parser = MarkdownParser()
    md_content = """# Main Title
Intro text.

## Section 1
Text in section 1.
![](image1.png)

### Subsection 1.1
Text in 1.1.
| col1 | col2 |
| --- | --- |
| val1 | val2 |

## Section 2
```python
print("hello")
```
"""
    root = parser.parse(md_content)
    
    assert root.title == "Root"
    assert len(root.children) == 1
    
    main_section = root.children[0]
    assert main_section.title == "Main Title"
    assert len(main_section.children) == 2
    
    s1 = main_section.children[0]
    assert s1.title == "Section 1"
    assert s1.image_count == 1
    assert len(s1.children) == 1
    
    ss11 = s1.children[0]
    assert ss11.title == "Subsection 1.1"
    assert ss11.table_count == 1
    
    s2 = main_section.children[1]
    assert s2.title == "Section 2"
    assert s2.code_block_count == 1

if __name__ == "__main__":
    test_markdown_parser_structure()
    print("Test passed!")
