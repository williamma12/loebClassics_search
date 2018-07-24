from contextlib import closing
import os.path
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
    

def get_citation_data(url, save=True, data_path='data/'):
    '''Get citation data of the book
    
    Parameter
    ---------
    url : str
        String containing url of the first page of the book
    save : boolean
        save the visited pages to drive
    data_path : string
        path to save the pages and where the saved data is
    
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
    
    # Get DOI number of work
    doi_data = html.findAll('div', {'class': 'doi'})
    if doi_data is None:
        raise RequestException("Could not find doi data")
    for datum in doi_data:
        if is_tag(datum):
            text = datum.get_text()
            if 'DOI' in text:
                citation_data['DOI'] = text.split(" ")[1]
    
    # Get work title
    title_data = html.findAll('span', {'class': 'workTitle'})
    if title_data is None:
        raise RequestException("Could not find title data")
    for datum in title_data:
        if is_tag(datum):
            citation_data['Title'] = datum.get_text()
            
    # Get volume number
    volume_data = html.find_all('div', {'class': 'volumeLoc'})
    if volume_data is None:
        raise RequestException("Could not find volume data")
    for datum in volume_data:
        if is_tag(datum) and datum.name == 'div':
            for div_child in datum.children:
                if is_tag(div_child) and div_child.name == 'h2':
                    for child in div_child.children:
                        if is_tag(child) and child.name == 'a':
                            citation_data['Volume'] = child.get_text()
        
    # Get the url for the print edition for more of the citation data
    for link in html.find_all('a'):
        if link.get_text() == "View cloth edition":
            purchase_url = link.get('href')
    if purchase_url is None:
        raise RequestException("Could not find cloth edition url")
    purchase_response = get_html(purchase_url)
    if purchase_response is None:
        raise ValueError("Bad purchase url")
    purchase_html = BeautifulSoup(purchase_response, 'html.parser')
    
    # Get the author and translator data
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
    
    # Get remaining book meta data (currently only ISBN and publication date)
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


def is_english(s):
    try:
        s.encode(encoding='utf-8').decode('ascii')
    except UnicodeDecodeError:
        return False
    else:
        return True
    
    
def search_book(words, url, num_pages=999999999, save=True, data_path='data/'):
    '''Get the surrounding lines around each appearence of a word in the words list
    
    Parameters
    ----------
    url : str
        url of the book
    words : list
        list containing desired words
    num_pages : int
        number of pages to look at or until end of book
    save : boolean
        save the visited pages to drive
    data_path : string
        path to save the pages and where the saved data is
    
    Returns
    -------
    Dataframe containing all appearences of the word in its surrounding paragraph
    '''
    citation_data = get_citation_data(url)
    results = list()
    
    # Generate print url with page number iteration
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
    
    # Iterate through pages
    count = 0
    while count < num_pages:
        page_link = link.format(page) + "&print"
        file_path = data_path+citation_data['Volume']+"_"+str(page)+".html"
        
        # Check if saved locally
        if os.path.isfile(file_path):
            with open(file_path, 'r') as file:
                response = file.read()
            if response is None:
                break;
            html = BeautifulSoup(response, 'html.parser')
        else:
            response = get_html(page_link)
            if response is None:
                break;
            html = BeautifulSoup(response, 'html.parser')
            if save:
                with open(file_path, 'w+') as file:
                    file.write(str(html))
        
        # Make sure the page exists
        try:
            for div in html.findAll('h1', {'class': 't-display-1', 'id': 'pagetitle'}):
                if is_tag(div) and div.get_text() == "Page not found":
                    break;
        except:
            pass
        
        # Search page for word
        for section in html.findAll('section', {'class': 'div2'}):
            if is_tag(section):
                for child in section.children:
                    if is_tag(child) and child.name == 'p':
                        text = child.get_text().replace("\n", " ")
                        for word in words:
                            if '{}'.format(word) in text:
                                if is_english(word):
                                    results.append([page, word, text])
                                else:
                                    results.append([page-1, word, text])
        page += 2
        count += 1
    
    if len(results) > 0:
        citation_df = pd.DataFrame().append(pd.Series(citation_data), ignore_index=True)
        results = pd.DataFrame(results)
        results.columns = ['Page Number', 'Word', 'Paragraph']
        citation_df['key'] = 1
        results['key'] = 1

        results = pd.merge(citation_df, results, on='key').drop(['key'], axis=1)
    else:
        results = pd.DataFrame()
        
    return results


def search_browse(url, **kwargs):
    '''Search through works listed on the search results (at URL) in a 
    loeb classics website search
    
    Parameter
    ---------
    words : list
        list of words to look for
    **kwargs
        arguments passed to search_book
    
    Returns
    -------
    Returns results of search_book for url and kwargs as one dataframe
    '''
    response = get_html(url)
    if response is None:
        raise ValueError("Bad author URL")
    html = BeautifulSoup(response, 'html.parser')
    
    links = list()
    results = pd.DataFrame()
    
    # Get links to the books
    for div1 in html.findAll('div', {'class': 's-pt-2', 'id': 'searchContent'}):
        if is_tag(div1):
            for a1 in div1.find_all('a'):
                if is_tag(a1):
                    link = 'https://www.loebclassics.com' + a1.get('href')
                    for span in a1.findAll('span', {'class': 'workTitle'}):
                        links.append(link)
                        break
    
    # Search books in links
    for link in links:
        df = search_book(url=link, **kwargs)
        if results.shape == (0, 0):
            results = df
        else:
            results = results.append(df, ignore_index=True)
    
    return results
    
    
def save_results(results, path="results/", delimiter="_"):
    '''Saves the results to path giving each volume its own csv file
    
    Parameters
    ----------
    results : Pandas dataframe
        Dataframe with data to save to csv
        
    path : string
        path to save the csv file to
    
    delimiter : string
        delimiter for the csv file
        
    Returns
    -------
    None
    '''
    for volume in results['Volume'].unique():
        volume_df = results[results['Volume'] == volume]
        # authors = volume_df['Author'].unique()
        titles = volume_df['Title'].unique()
        words = volume_df['Word'].unique()
        # file_name = "{}-{}-{}-{}.csv".format("_".join(authors), "_".join(titles), volume, "_".join(words))
        file_name = "{}-{}-{}.csv".format("_".join(titles), volume, "_".join(words))
        volume_df.to_csv(path+file_name, sep=delimiter)

    
def run(url, book, search_args, save_args):
    '''User facing function that runs the scraper and saves the results
    
    Parameter
    ---------
    url : string
        String containing the url to search
        
    book : boolean
        True if it is directly the book, otherwise, it is assumed that it is a browse result
    
    search_args : dict
        Dictionary containing the keyworded arguments for search function. If book, then the 
        search function is search_book, else, the search function is search_browse
        
    save_args : dict
        Dictionary containing the keyworded arguments for save_results
    
    Return
    ------
    Returns the number of results 
    '''
    if book:
        result = search_book(url, **search_args)
    else:
        result = search_browse(url, **search_args)
    
    save_results(result, **save_args)
    
    return result.shape[0]

if __name__ == "__main__":
    url = 'https://www.loebclassics.com/browse?t1=author.addaeus.of.macedonia'
    book = False
    search_args = {'words': ['Ἴος', 'Ios'],
                  'num_pages': 1,
                  'save': True}
    save_args = {'path': 'results/',
                'delimiter': '_'}

    n_results = run(url, book, search_args, save_args)
    print("GOT {} RESULTS".format(n_results))

