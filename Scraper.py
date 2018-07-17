from contextlib import closing
import re
import requests
from requests.exceptions import RequestException

from bs4 import BeautifulSoup
import pandas as pd

def is_good_response(resp):
    """
    Checks if the response is HTML
    """
    content_type = resp.headers['Content-Type'].lower()
    return (resp.status_code == 200 
            and content_type is not None 
            and content_type.find('html') > -1)


def get_html(url):
    '''
    Gets the html data of the url
    '''
    try:
        with closing(requests.get(url, stream=True)) as resp:
            if is_good_response(resp):
                return resp.content
            else:
                return None

    except RequestException as e:
        log_error('Error during requests to {0} : {1}'.format(url, str(e)))
        return None
    
def is_tag(obj):
    '''
    Checks if obj is a beautiful soup tag object
    '''
    return type(obj) == type(BeautifulSoup('<b>Test Tag</b>', 'html.parser').b)
    

def get_citation_data(url):
    '''Get citation data of the book
    
    Parameter
    ---------
    url : str
        String containing url of the first page of the book
    
    Returns
    -------
    Dictionary containing citation data in key-value pairs
    
    '''
    citation_data = dict()
    
    response = get_html(url)
    if response is None:
        raise ValueError("Bad book URL")
    
    purchase_url = None
    html = BeautifulSoup(response, 'html.parser')
    
    doi_data = html.findAll('div', {'class': 'doi'})
    if doi_data is None:
        raise RequestException("Could not find doi data")

    for datum in doi_data:
        if is_tag(datum):
            text = datum.get_text()
            
            if 'DOI' in text:
                citation_data['DOI'] = text.split(" ")[1]
    
    title_data = html.findAll('span', {'class': 'workTitle'})
    if title_data is None:
        raise RequestException("Could not find title data")
    
    for datum in title_data:
        if is_tag(datum):
            citation_data['Title'] = datum.get_text()
        
    for link in html.find_all('a'):
        if link.get_text() == "View cloth edition":
            purchase_url = link.get('href')
            
    if purchase_url is None:
        raise RequestException("Could not find cloth edition url")
        
    purchase_response = get_html(purchase_url)
    if purchase_response is None:
        raise ValueError("Bad purchase url")
    
    purchase_html = BeautifulSoup(purchase_response, 'html.parser')
    
    authors = purchase_html.find(id='authorList')
    if authors is None:
        raise RequestException("Missing authors list")
    
    for author in authors:
        if is_tag(author):
            text = author.get_text()
            key = ''
            value = ''
            if "by" in text:
                by_found = False
                for word in text.split(" "):
                    if by_found:
                        value += word + " "
                    else: 
                        key += word + ' '
                    if word == "by":
                        by_found = True
            else:
                key = 'Author'
                value = text
                
            citation_data[key.strip()] = value.strip()
    
    book_data = purchase_html.find(id='bookMeta')
    if book_data is None:
        raise RequestException("Missing book data")
    
    for datum in book_data:
        if is_tag(datum):
            text = datum.get_text()
            
            if 'ISBN' in text:
                citation_data['ISBN'] = text.split(" ")[1]
            elif 'Publication' in text:
                citation_data['Date'] = " ".join(text.split(" ")[1:])
        
    return citation_data

def search_book(words, url, max_pages=999999999):
    '''Get the surrounding lines around each appearence of a word in the words list
    
    Parameters
    ----------
    url : str
        url of the book
    words : list
        list containing desired words
    max_pages : int
        maximum pages to look at
    
    Returns
    -------
    Dataframe containing all appearences of the word in its surrounding paragraph
    '''
    citation_data = get_citation_data(url)
    results = list()
    
    link = list()
    page = 0
    prev_part = str()
    for url_part in url.split("."):
        three_chars = list(url_part)[0:3]
        if ''.join(three_chars) == 'xml':
            page = int(prev_part)
            link.append("{}")
        else:
            link.append(prev_part)
        prev_part = url_part
    link.append(prev_part)
    link = ".".join(link[1:])
    
    count = 0
    while count < max_pages:
        page_link = link.format(page)
        response = get_html(page_link+"&print")
        if response is None:
            break;
        html = BeautifulSoup(response, 'html.parser')
        
        try:
            for div in html.findAll('h1', {'class': 't-display-1', 'id': 'pagetitle'}):
                if is_tag(div) and div.get_text() == "Page not found":
                    break;
        except:
            pass
        
        for div1 in html.findAll('div', {'id': 'rectoContentPanelId', 'class': 'recto panel'}):
            if is_tag(div1):
                for div2 in div1.findAll('section', {'class': 'div2'}):
                    for child in div2.children:
                        if is_tag(child) and child.name == 'p':
                            text = child.get_text()
                            for word in words:
                                if ' {}'.format(word) in text:
                                    results.append([page, word, text])
        
        page += 2
        count += 1
    
    citation_df = pd.DataFrame().append(pd.Series(citation_data), ignore_index=True)
    results = pd.DataFrame(results)
    results.columns = ['Page Number', 'Word', 'Paragraph']
    citation_df['key'] = 1
    results['key'] = 1
    
    results = pd.merge(citation_df, results, on='key').drop(['key'], axis=1)
    return results

if __name__ == '__main__':
    search_result = search_book(['votive'], 
            "https://www.loebclassics.com/view/achilles_tatius-leucippe_clitophon/1969/pb_LCL045.3.xml?result=1&rskey=BWv00J", 
            1)
    print("DDD")
    search_result.to_csv("loebClassics_searchResult.csv")
    print("DDD")

