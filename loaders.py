import os
from time import sleep
import streamlit as st
from langchain_community.document_loaders import (WebBaseLoader,
                                                  YoutubeLoader, 
                                                  CSVLoader, 
                                                  PyPDFLoader, 
                                                  TextLoader)
from fake_useragent import UserAgent

def carrega_site(url):
    
    if not url or url.strip() == '':
        st.error('URL não pode ser vazia')
        st.stop()
        
   
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        print(f"Added https:// scheme to URL: {url}")
    
    documento = ''
    for i in range(5):
        try:
            
            ua = UserAgent().random
            
            
            loader = WebBaseLoader(
                url,
                raise_for_status=True,
                header_template={"User-Agent": ua}
            )
            
            print(f"Attempt {i+1} with User-Agent: {ua}")
            lista_documentos = loader.load()
            documento = '\n\n'.join([doc.page_content for doc in lista_documentos])
            print(f"Successfully loaded content from {url}")
            break
        except Exception as e:
            print(f'Error loading site (attempt {i+1}): {str(e)}')
            sleep(3)
    
    if documento == '':
        st.error(f'Não foi possível carregar o site: {url}')
        st.stop()
    
    return documento

def carrega_youtube(video_url):
    # Extract video ID from the URL
    if "v=" in video_url:
        video_id = video_url.split("v=")[-1]
    else:
        video_id = video_url  # Assume it's already a video ID
    
    loader = YoutubeLoader(video_id, add_video_info=False, language=['pt'])
    lista_documentos = loader.load()
    documento = '\n\n'.join([doc.page_content for doc in lista_documentos])
    return documento


def carrega_csv(caminho):
    loader = CSVLoader(caminho)
    lista_documentos = loader.load()
    documento = '\n\n'.join([doc.page_content for doc in lista_documentos])
    return documento

def carrega_pdf(caminho):
    loader = PyPDFLoader(caminho)
    lista_documentos = loader.load()
    documento = '\n\n'.join([doc.page_content for doc in lista_documentos])
    return documento

def carrega_txt(caminho):
    loader = TextLoader(caminho)
    lista_documentos = loader.load()
    documento = '\n\n'.join([doc.page_content for doc in lista_documentos])
    return documento
