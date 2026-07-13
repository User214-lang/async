import pytest
from bs4 import BeautifulSoup
from parser import HTMLParser

@pytest.fixture
def parser():
    return HTMLParser()


# Парсинг валиндого html
@pytest.mark.asyncio
async def test_parse_valid_html(parser):
    html = """
    <html>
        <head>
            <title>Test Page</title>
            <meta name="description" content="Test description">
            <meta name="keywords" content="test, parser">
        </head>
        <body>
            <h1>Main Header</h1>
            <h2>Sub Header</h2>
            <p>Some text here.</p>
            <a href="/page1">Link 1</a>
            <a href="https://external.com">External</a>
            <img src="image.png" alt="image">
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
            <table>
                <tr><td>Cell 1</td><td>Cell 2</td></tr>
            </table>
        </body>
    </html>
    """
    url = "https://example.com"
    result = await parser.parse_html(html, url)

    assert result['url'] == url
    assert result['title'] == "Test Page"
    assert result['description'] == "Test description"
    assert result['keywords'] == "test, parser"
    assert "Some text here" in result['text']
    assert len(result['links']) == 2
    assert "https://example.com/page1" in result['links']
    assert "https://external.com" in result['links']
    assert len(result['images']) == 1
    assert result['images'][0]['src'] == "image.png"
    assert result['images'][0]['alt'] == "image"
    assert result['headings']['h1'] == ["Main Header"]
    assert result['headings']['h2'] == ["Sub Header"]
    assert len(result['tables']) == 1
    assert result['tables'][0][0] == ["Cell 1", "Cell 2"]
    assert result['lists']['ul'] == ["Item 1", "Item 2"]


# Обработка некорректного html
@pytest.mark.asyncio
async def test_parse_broken_html(parser):
    broken_html = "<html><body><h1>Unclosed tag</p>"
    url = "https://example.com"
    result = await parser.parse_html(broken_html, url)

    assert result['url'] == url
    assert 'title' in result
    assert 'text' in result
    assert 'error' not in result or result['error'] == ''


#Извлечение ссылок
def test_extract_links(parser):
    html = """
    <html>
        <body>
            <a href="/relative">Relative</a>
            <a href="https://absolute.com">Absolute</a>
            <a href="#anchor">Anchor</a>
            <a href="javascript:void(0)">JS</a>
            <a href="http://example.com">HTTP</a>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, 'lxml')
    base_url = "https://base.com"
    links = parser.extract_links(soup, base_url, filter_external=False)

    assert "https://base.com/relative" in links
    assert "https://absolute.com" in links
    assert "http://example.com" in links


#Относительные url в абсолютные
def test_convert_relative_urls(parser):
    html = """
    <html>
        <body>
            <a href="/path/to/page">Page</a>
            <a href="page2">Page2</a>
            <a href="../up">Up</a>
            <a href="//example.com">Protocol-relative</a>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, 'lxml')
    base_url = "https://site.com/dir/subdir/"
    links = parser.extract_links(soup, base_url, filter_external=False)

    assert "https://site.com/path/to/page" in links
    assert "https://site.com/dir/subdir/page2" in links
    assert "https://site.com/dir/up" in links
    assert "https://example.com" in links


#Фильтрация внешних ссылок
def test_filter_external_links(parser):
    html = """
    <html>
        <body>
            <a href="/internal">Internal</a>
            <a href="https://external.com">External</a>
            <a href="http://another.com">Another</a>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, 'lxml')
    base_url = "https://mysite.com"
    links = parser.extract_links(soup, base_url, filter_external=True)

    assert "https://mysite.com/internal" in links
    assert "https://external.com" not in links
    assert "http://another.com" not in links


#Битый html
@pytest.mark.asyncio
async def test_broken_html_no_exception(parser):
    very_broken = "<div><p>Unclosed <span>"
    result = await parser.parse_html(very_broken, "https://test.com")
    assert isinstance(result, dict)
    assert 'text' in result