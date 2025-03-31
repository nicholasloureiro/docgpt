import tempfile
import os
import sqlite3
import datetime
import uuid
import streamlit as st
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from loaders import *


TIPOS_ARQUIVOS_VALIDOS = ["Site", "Youtube", "Pdf", "Csv", "Txt"]

# Default to OpenAI and gpt-4o-mini
DEFAULT_PROVEDOR = "OpenAI"
DEFAULT_MODELO = "gpt-4o-mini"

# Database setup
DB_PATH = "docgpt.db"


def init_database():
    """Initialize the SQLite database with required tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create chats table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS chats (
        chat_id TEXT PRIMARY KEY,
        title TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        file_type TEXT,
        file_path TEXT,
        file_url TEXT
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT PRIMARY KEY,
        chat_id TEXT,
        role TEXT,
        content TEXT,
        timestamp TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES chats (chat_id)
    )
    """
    )

    conn.commit()
    conn.close()


def save_file(file, file_type):
    """Save an uploaded file to disk and return the path."""
    if file_type == "Site" or file_type == "Youtube":
        return None, file

    os.makedirs("uploads", exist_ok=True)

    # Get original filename without extension
    original_filename = os.path.splitext(file.name)[0]

    # Add timestamp to filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    new_filename = f"{original_filename}_{timestamp}"

    # Add appropriate extension based on file type
    file_ext = "." + file_type.lower()
    filename = f"uploads/{new_filename}{file_ext}"

    with open(filename, "wb") as f:
        f.write(file.read())
        file.seek(0)  # Reset file pointer for further processing

    return filename, None


def create_new_chat(file_type, file_path=None, file_url=None):
    """Create a new chat in the database."""
    chat_id = str(uuid.uuid4())
    now = datetime.datetime.now()

    title = (
        file_url
        if (file_type == "Site" or file_type == "Youtube")
        else os.path.basename(file_path)
    )
    # Create a readable title
    if file_type == "Site":
        title = (
            f"Site: {file_url[:30]}..." if len(file_url) > 30 else f"Site: {file_url}"
        )
    elif file_type == "Youtube":
        title = (
            f"YouTube: {file_url[:30]}..."
            if len(file_url) > 30
            else f"YouTube: {file_url}"
        )
    else:
        title = f"{file_type}: {os.path.basename(file_path)}"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    INSERT INTO chats (chat_id, title, created_at, updated_at, file_type, file_path, file_url)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (chat_id, title, now, now, file_type, file_path, file_url),
    )
    conn.commit()
    conn.close()

    return chat_id


def update_chat_title(chat_id, new_title):
    """Update the title of a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    UPDATE chats SET title = ? WHERE chat_id = ?
    """,
        (new_title, chat_id),
    )
    conn.commit()
    conn.close()


def get_chat_list():
    """Get a list of all chats from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT chat_id, title, created_at, file_type
    FROM chats
    ORDER BY updated_at DESC
    """
    )
    chats = cursor.fetchall()
    conn.close()
    return chats


def get_chat(chat_id):
    """Get chat details from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT * FROM chats WHERE chat_id = ?
    """,
        (chat_id,),
    )
    chat = cursor.fetchone()
    conn.close()
    return chat


def save_message(chat_id, role, content):
    """Save a message to the database."""
    message_id = str(uuid.uuid4())
    now = datetime.datetime.now()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Save the message
    cursor.execute(
        """
    INSERT INTO messages (message_id, chat_id, role, content, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """,
        (message_id, chat_id, role, content, now),
    )

    # Update the chat's updated_at timestamp
    cursor.execute(
        """
    UPDATE chats SET updated_at = ? WHERE chat_id = ?
    """,
        (now, chat_id),
    )

    conn.commit()
    conn.close()


def get_messages(chat_id):
    """Get all messages for a chat from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT role, content FROM messages
    WHERE chat_id = ?
    ORDER BY timestamp
    """,
        (chat_id,),
    )
    messages = cursor.fetchall()
    conn.close()
    return messages


def carrega_arquivos(tipo_arquivo, arquivo):
    if tipo_arquivo == "Site":
        documento = carrega_site(arquivo)
    if tipo_arquivo == "Youtube":
        documento = carrega_youtube(arquivo)
    if tipo_arquivo == "Pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp:
            temp.write(arquivo.read())
            nome_temp = temp.name
        arquivo.seek(0)  # Reset file pointer for further processing
        documento = carrega_pdf(nome_temp)
    if tipo_arquivo == "Csv":
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temp:
            temp.write(arquivo.read())
            nome_temp = temp.name
        arquivo.seek(0)  # Reset file pointer for further processing
        documento = carrega_csv(nome_temp)
    if tipo_arquivo == "Txt":
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp:
            temp.write(arquivo.read())
            nome_temp = temp.name
        arquivo.seek(0)  # Reset file pointer for further processing
        documento = carrega_txt(nome_temp)
    return documento


def carrega_modelo(tipo_arquivo, arquivo, chat_id=None):
    load_dotenv()

    api_key = os.getenv('OPENAI_API_KEY')

    print(api_key)
    print(f"aqui:{api_key}")
    if not api_key:
        st.error(
            "API key not found in environment variables. Please set OPENAI_API_KEY."
        )
        st.stop()

    documento = carrega_arquivos(tipo_arquivo, arquivo)

    system_message = """Você é um assistente amigável chamado DocGPT.
    Você possui acesso às seguintes informações vindas 
    de um documento {}: 

    ####
    {}
    ####

    Utilize as informações fornecidas para basear as suas respostas.

    Sempre que houver $ na sua saída, substita por S.

    Se a informação do documento for algo como "Just a moment...Enable JavaScript and cookies to continue" 
    sugira ao usuário carregar novamente o Oráculo!""".format(
        tipo_arquivo, documento
    )

    template = ChatPromptTemplate.from_messages(
        [
            ("system", system_message),
            ("placeholder", "{chat_history}"),
            ("user", "{input}"),
        ]
    )
    chat = ChatOpenAI(model=DEFAULT_MODELO, api_key=api_key)
    chain = template | chat

    st.session_state["chain"] = chain

    # If this is a new document, create a new chat
    if not chat_id:
        if tipo_arquivo in ["Site", "Youtube"]:
            file_path, file_url = None, arquivo
        else:
            file_path, file_url = save_file(arquivo, tipo_arquivo)

        chat_id = create_new_chat(tipo_arquivo, file_path, file_url)

    st.session_state["current_chat_id"] = chat_id
    # Initialize or reset memory for this chat
    st.session_state["memoria"] = ConversationBufferMemory()

    # Load existing messages if any
    messages = get_messages(chat_id)
    for role, content in messages:
        if role == "human":
            st.session_state["memoria"].chat_memory.add_user_message(content)
        elif role == "ai":
            st.session_state["memoria"].chat_memory.add_ai_message(content)


def pagina_chat():
    st.header("🤖 DocGPT", divider=True)

    chain = st.session_state.get("chain")
    current_chat_id = st.session_state.get("current_chat_id")

    if chain is None or current_chat_id is None:
        st.info(
            "Adicione um documento para ser analisado ou selecione uma conversa existente..."
        )
        st.stop()

    # Get current chat details
    chat_details = get_chat(current_chat_id)
    _, current_title, _, _, file_type, _, _ = chat_details

    # Add rename option
    with st.expander("⚙️ Configurações da conversa"):
        col1, col2 = st.columns([3, 1])
        new_title = col1.text_input(
            "Renomear documento:", value=current_title, key="rename_input"
        )
        if col2.button("Salvar", key="rename_button"):
            update_chat_title(current_chat_id, new_title)
            st.success("Nome atualizado com sucesso!")
            st.rerun()

    memoria = st.session_state.get("memoria")

    # Display chat messages
    for mensagem in memoria.buffer_as_messages:
        chat = st.chat_message(mensagem.type)
        chat.markdown(mensagem.content)

    # Chat input
    input_usuario = st.chat_input(f"Faça uma pergunta sobre o documento")
    if input_usuario:
        chat = st.chat_message("human")
        chat.markdown(input_usuario)

        # Save user message to database
        save_message(current_chat_id, "human", input_usuario)

        chat = st.chat_message("ai")
        resposta = chat.write_stream(
            chain.stream(
                {"input": input_usuario, "chat_history": memoria.buffer_as_messages}
            )
        )

        # Save AI response to database
        save_message(current_chat_id, "ai", resposta)

        memoria.chat_memory.add_user_message(input_usuario)
        memoria.chat_memory.add_ai_message(resposta)
        st.session_state["memoria"] = memoria


def render_chat_list(container):
    """Render the chat list with a professional look and search functionality."""
    container.subheader("💬 Conversas")

    # Add "New Chat" button at the top
    if container.button(
        "🆕 Nova Conversa", use_container_width=True, key="new_chat_btn"
    ):
        # Clear current chat
        if "current_chat_id" in st.session_state:
            del st.session_state["current_chat_id"]
        if "chain" in st.session_state:
            del st.session_state["chain"]
        st.rerun()

    # Add search functionality
    search_term = container.text_input(
        "🔍 Buscar por título ou data (DD/MM/YYYY)", key="chat_search"
    )

    container.divider()

    # Get all chats
    chats = get_chat_list()

    # Filter chats based on search term
    if search_term:
        filtered_chats = []
        for chat in chats:
            chat_id, title, created_at, file_type = chat
            date = datetime.datetime.fromisoformat(created_at)
            date_str = date.strftime("%d/%m/%Y")

            # Check if search term is in title or matches date format
            if (search_term.lower() in title.lower()) or (search_term in date_str):
                filtered_chats.append(chat)
        chats = filtered_chats

    # Display chat list
    if not chats:
        if search_term:
            container.warning(f"Nenhuma conversa encontrada para '{search_term}'.")
        else:
            container.info("Nenhuma conversa encontrada.")
    else:
        # Show number of results if there's a search
        if search_term:
            container.success(f"{len(chats)} conversa(s) encontrada(s).")

        for chat_id, title, created_at, file_type in chats:
            # Format the date to be more readable
            date = datetime.datetime.fromisoformat(created_at)
            date_str = date.strftime("%d/%m/%Y %H:%M")

            # Create a container for each chat entry
            chat_container = container.container()
            col1, col2 = chat_container.columns([4, 1])

            # Add icon based on file type
            icon = "📄"
            if file_type == "Site":
                icon = "🌐"
            elif file_type == "Youtube":
                icon = "▶️"
            elif file_type == "Pdf":
                icon = "📑"
            elif file_type == "Csv":
                icon = "📊"

            # Show the chat title and date
            is_selected = st.session_state.get("current_chat_id") == chat_id
            title_style = "font-weight: bold;" if is_selected else ""

            if col1.button(
                f"{icon} {title}", key=f"chat_{chat_id}", use_container_width=True
            ):
                # Load the selected chat
                chat_details = get_chat(chat_id)
                _, _, _, _, file_type, file_path, file_url = chat_details

                # Load the file
                if file_type in ["Site", "Youtube"]:
                    arquivo = file_url
                else:
                    # Open the file from disk
                    with open(file_path, "rb") as f:
                        arquivo_conteudo = f.read()

                    # Create object after file is read into memory
                    arquivo = type(
                        "obj",
                        (object,),
                        {"read": lambda: arquivo_conteudo, "seek": lambda x: None},
                    )

                carrega_modelo(file_type, arquivo, chat_id)
                st.rerun()

            # Delete button for each chat
            if col2.button("🗑️", key=f"del_{chat_id}"):
                # Implement delete functionality
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                # Delete messages first (foreign key constraint)
                cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))

                # Delete the chat
                cursor.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))

                conn.commit()
                conn.close()

                # If the deleted chat was the current one, clear the current chat
                if st.session_state.get("current_chat_id") == chat_id:
                    if "current_chat_id" in st.session_state:
                        del st.session_state["current_chat_id"]
                    if "chain" in st.session_state:
                        del st.session_state["chain"]

                st.rerun()

            # Add a small date label
            chat_container.caption(f"{date_str}")

            # Add a subtle divider between chats
            container.markdown("---")


def file_upload_section(container):
    """Render the file upload section with dynamic inputs based on file type."""
    container.subheader("📁 Carregar Documento")

    # Create a session state to track changes
    if "previous_tipo_arquivo" not in st.session_state:
        st.session_state["previous_tipo_arquivo"] = None

    # Select file type outside of any form
    tipo_arquivo = container.selectbox(
        "Selecione o tipo de arquivo", TIPOS_ARQUIVOS_VALIDOS
    )

    # Check if file type changed
    file_type_changed = tipo_arquivo != st.session_state["previous_tipo_arquivo"]
    st.session_state["previous_tipo_arquivo"] = tipo_arquivo

    # Create unique keys for each input type to avoid conflicts
    arquivo = None
    if tipo_arquivo == "Site":
        arquivo = container.text_input("Digite a url do site", key="site_input")
    elif tipo_arquivo == "Youtube":
        arquivo = container.text_input("Digite a url do vídeo", key="youtube_input")
    elif tipo_arquivo == "Pdf":
        arquivo = container.file_uploader(
            "Faça o upload do arquivo pdf", type=["pdf"], key="pdf_uploader"
        )
    elif tipo_arquivo == "Csv":
        arquivo = container.file_uploader(
            "Faça o upload do arquivo csv", type=["csv"], key="csv_uploader"
        )
    elif tipo_arquivo == "Txt":
        arquivo = container.file_uploader(
            "Faça o upload do arquivo txt", type=["txt"], key="txt_uploader"
        )

    # Submit button outside of a form
    submit_button = container.button(
        "Carregar Documento", use_container_width=True, key="submit_doc"
    )

    # Process the upload when button is clicked
    if submit_button and arquivo:
        carrega_modelo(tipo_arquivo, arquivo)
        container.success("Documento carregado com sucesso!")
        st.rerun()

    return tipo_arquivo, arquivo


def main():
    # Configure the page with a wider layout
    st.set_page_config(
        page_title="DocGPT",
        layout="wide",
        initial_sidebar_state="expanded",  # Make sure sidebar is expanded by default
    )

    # Initialize the database
    init_database()

    # Create a two-column layout
    left_col, right_col = st.columns([1, 3])

    with left_col:
        # Create a container for the file upload section - prominently displayed at the top
        upload_container = st.container()
        with upload_container:
            file_upload_section(upload_container)

        st.divider()

        # Create a container for the chat list
        chat_list_container = st.container()
        with chat_list_container:
            render_chat_list(chat_list_container)

        # Add the clear conversation button at the bottom
        if st.button("🧹 Apagar Histórico de Conversa", use_container_width=True):
            if "current_chat_id" in st.session_state:
                # Delete all messages for the current chat
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM messages WHERE chat_id = ?",
                    (st.session_state["current_chat_id"],),
                )
                conn.commit()
                conn.close()

                # Reset memory
                st.session_state["memoria"] = ConversationBufferMemory()
                st.rerun()

    with right_col:
        # Display the chat interface
        pagina_chat()


if __name__ == "__main__":
    main()
