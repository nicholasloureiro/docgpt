import tempfile
import os
import sqlite3
import datetime
import uuid
import streamlit as st
import hashlib
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from loaders import *

# Add these imports
import pickle
import base64

TIPOS_ARQUIVOS_VALIDOS = ["Site", "Pdf", "Csv", "Txt"]

# Default to OpenAI and gpt-4o-mini
DEFAULT_PROVEDOR = "OpenAI"
DEFAULT_MODELO = "gpt-4o"

# Database setup
DB_PATH = "docgpt.db"

# Custom CSS for DeepSeek-like styling
def inject_custom_css():
    st.markdown("""
    <style>
        /* Main container styling */
        .stApp {
            background-color: #f5f5f5;
        }
        
        /* Sidebar styling */
        [data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e0e0e0;
        }
        
        /* Chat message styling */
        .stChatMessage {
            padding: 12px 16px;
            border-radius: 12px;
            margin-bottom: 8px;
            max-width: 85%;
        }
        
        /* User message styling */
        [data-testid="stChatMessage-user"] {
            background-color: #f0f7ff;
            margin-left: auto;
            border-bottom-right-radius: 4px;
        }
        
        /* AI message styling */
        [data-testid="stChatMessage-assistant"] {
            background-color: #ffffff;
            border: 1px solid #e0e0e0;
            border-bottom-left-radius: 4px;
        }
        
        /* Input box styling */
        .stTextInput input, .stTextArea textarea {
            border-radius: 12px;
            padding: 12px;
        }
        
        /* Button styling */
        .stButton>button {
            border-radius: 12px;
            padding: 8px 16px;
            background-color: #4f46e5;
            color: white;
        }
        
        .stButton>button:hover {
            background-color: #4338ca;
        }
        
        /* File uploader styling */
        .stFileUploader>div {
            border: 2px dashed #e0e0e0;
            border-radius: 12px;
            padding: 20px;
        }
        
        /* Tab styling */
        .stTabs [role="tablist"] {
            gap: 8px;
        }
        
        .stTabs [role="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 8px 16px;
            background-color: #f0f0f0;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #4f46e5;
            color: white;
        }
        
        /* Chat list item styling */
        .chat-item {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .chat-item:hover {
            background-color: #f0f0f0;
        }
        
        .chat-item.active {
            background-color: #e0e7ff;
        }
        
        /* Hide Streamlit branding */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# Add this function to help with session persistence
def get_session_cookie_key(user_id):
    """Generate a unique cookie key for a user's session."""
    return f"docgpt_session_{user_id}"

def save_session_cookie(user_id, username):
    """Save session data in a cookie."""
    session_data = {
        "authenticated": True,
        "user_id": user_id,
        "username": username,
        "created_at": datetime.datetime.now().isoformat()  # Add timestamp for expiry check
    }
    cookie_key = get_session_cookie_key(user_id)
    cookie_value = base64.b64encode(pickle.dumps(session_data)).decode()
    
    # Set cookie in session state
    st.session_state[cookie_key] = cookie_value
    
    # Store in normal session state too
    st.session_state["authenticated"] = True
    st.session_state["user_id"] = user_id
    st.session_state["username"] = username
    
    # Debug info
    print(f"Session cookie saved for user: {username}")

def load_session_from_cookie():
    """Try to load session data from cookies."""
    # Check if we're already authenticated in this session
    if st.session_state.get("authenticated"):
        return True
        
    # Look for any session cookies
    for key in list(st.session_state.keys()):
        if key.startswith("docgpt_session_"):
            try:
                cookie_value = st.session_state[key]
                session_data = pickle.loads(base64.b64decode(cookie_value))
                
                # Validate session data
                if (session_data.get("authenticated") and 
                    session_data.get("user_id") and 
                    session_data.get("username")):
                    
                    # Restore session data
                    st.session_state["authenticated"] = session_data["authenticated"]
                    st.session_state["user_id"] = session_data["user_id"]
                    st.session_state["username"] = session_data["username"]
                    
                    # Refresh the cookie to extend its lifetime
                    save_session_cookie(session_data["user_id"], session_data["username"])
                    return True
            except Exception as e:
                print(f"Error loading session cookie: {e}")
                # Invalid cookie, remove it
                del st.session_state[key]
    
    return False

def clear_session_cookies():
    """Clear all session cookies."""
    for key in list(st.session_state.keys()):
        if key.startswith("docgpt_session_"):
            del st.session_state[key]

def init_database():
    """Initialize the SQLite database with required tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create users table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        created_at TIMESTAMP
    )
    """
    )

    # Create chats table with user_id field
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS chats (
        chat_id TEXT PRIMARY KEY,
        user_id TEXT,
        title TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        file_type TEXT,
        file_path TEXT,
        file_url TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
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


def hash_password(password):
    """Create a SHA-256 hash of the password."""
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(username, password):
    """Create a new user in the database."""
    user_id = str(uuid.uuid4())
    now = datetime.datetime.now()
    password_hash = hash_password(password)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
        INSERT INTO users (user_id, username, password_hash, created_at)
        VALUES (?, ?, ?, ?)
        """,
            (user_id, username, password_hash, now),
        )
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        # Username already exists
        success = False
    
    conn.close()
    return success, user_id if success else None


def authenticate_user(username, password):
    """Authenticate a user by username and password."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        """
    SELECT user_id, password_hash FROM users WHERE username = ?
    """,
        (username,),
    )
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result[1] == hash_password(password):
        return True, result[0]  # Authentication successful, return user_id
    return False, None


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


def create_new_chat(user_id, file_type, file_path=None, file_url=None):
    """Create a new chat in the database associated with a specific user."""
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
    INSERT INTO chats (chat_id, user_id, title, created_at, updated_at, file_type, file_path, file_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (chat_id, user_id, title, now, now, file_type, file_path, file_url),
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


def get_chat_list(user_id):
    """Get a list of all chats for a specific user from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT chat_id, title, created_at, file_type
    FROM chats
    WHERE user_id = ?
    ORDER BY updated_at DESC
    """,
        (user_id,),
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


def is_chat_owner(chat_id, user_id):
    """Check if the user is the owner of the chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT user_id FROM chats WHERE chat_id = ?
    """,
        (chat_id,),
    )
    result = cursor.fetchone()
    conn.close()
    
    return result and result[0] == user_id


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

        chat_id = create_new_chat(st.session_state["user_id"], tipo_arquivo, file_path, file_url)

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


def login_page():
    st.markdown(
        """
        <div style='text-align: center; margin-bottom: 30px;'>
            <h1 style='color: #4f46e5; font-size: 2.5rem;'>DocGPT</h1>
            <p style='color: #666; font-size: 1.1rem;'>Converse com seus documentos</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    with st.container():
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.container():
                st.markdown(
                    """

                    """,
                    unsafe_allow_html=True,
                )
                
                tab1, tab2 = st.tabs(["Login", "Cadastro"])
                
                with tab1:
                    with st.form("login_form"):
                        st.markdown("#### Acesse sua conta")
                        username = st.text_input("Nome de usuário", key="login_username")
                        password = st.text_input("Senha", type="password", key="login_password")
                        submit = st.form_submit_button("Entrar", use_container_width=True)
                        
                        if submit:
                            if not username or not password:
                                st.error("Por favor, preencha todos os campos")
                            else:
                                authenticated, user_id = authenticate_user(username, password)
                                if authenticated:
                                    # Save authentication to cookies for persistence
                                    save_session_cookie(user_id, username)
                                    st.success("Login realizado com sucesso!")
                                    st.rerun()
                                else:
                                    st.error("Nome de usuário ou senha incorretos")
                
                with tab2:
                    with st.form("register_form"):
                        st.markdown("#### Crie sua conta")
                        new_username = st.text_input("Nome de usuário", key="reg_username")
                        new_password = st.text_input("Nova senha", type="password", key="reg_password")
                        confirm_password = st.text_input("Confirme a senha", type="password", key="reg_confirm_password")
                        submit_reg = st.form_submit_button("Cadastrar", use_container_width=True)
                        
                        if submit_reg:
                            if not new_username or not new_password or not confirm_password:
                                st.error("Por favor, preencha todos os campos")
                            elif new_password != confirm_password:
                                st.error("As senhas não coincidem")
                            else:
                                success, user_id = create_user(new_username, new_password)
                                if success:
                                    st.success("Cadastro realizado com sucesso! Faça login para continuar.")
                                else:
                                    st.error("Nome de usuário já existe")
                
                st.markdown("</div>", unsafe_allow_html=True)
        
        



# Remove the logout button from pagina_chat()
def pagina_chat():
    # Header with logo
    col1, col2 = st.columns([1, 4])
    with col1:
        st.markdown(
            """
            <div style='display: flex; align-items: center; gap: 10px;'>
                <h2 style='color: #4f46e5; margin: 0;'>DocGPT</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        # User info without logout button
        st.markdown(
            f"""
            <div style='display: flex; justify-content: flex-end; align-items: center; gap: 10px;'>
                <span style='color: #666;'>Olá, {st.session_state['username']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

 

    chain = st.session_state.get("chain")
    current_chat_id = st.session_state.get("current_chat_id")

    if chain is None or current_chat_id is None:
        st.info(
            "Adicione um documento para ser analisado ou selecione uma conversa existente..."
        )
        st.stop()

    # Check if user is authorized to view this chat
    if not is_chat_owner(current_chat_id, st.session_state["user_id"]):
        st.error("Você não tem permissão para acessar esta conversa.")
        # Clear current chat
        if "current_chat_id" in st.session_state:
            del st.session_state["current_chat_id"]
        if "chain" in st.session_state:
            del st.session_state["chain"]
        st.stop()

    # Get current chat details
    chat_details = get_chat(current_chat_id)
    _, _, current_title, _, _, file_type, _, _ = chat_details

    # Chat container with subtle border
    with st.container():
        # Display chat messages in a container with max-width
        st.markdown(
            """
            <div style='max-width: 800px; margin: 0 auto;'>
            """,
            unsafe_allow_html=True,
        )
        
        memoria = st.session_state.get("memoria")

        # Display chat messages
        for mensagem in memoria.buffer_as_messages:
            chat = st.chat_message(mensagem.type)
            chat.markdown(mensagem.content)

        st.markdown("</div>", unsafe_allow_html=True)

        # Chat input at the bottom
        input_usuario = st.chat_input(f"Faça uma pergunta sobre o documento", key="chat_input")
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
    container.markdown("### Conversas")

    # Add "New Chat" button at the top
    if container.button(
        "➕ Nova Conversa", use_container_width=True, key="new_chat_btn", 
        help="Comece uma nova conversa"
    ):
        # Clear current chat
        if "current_chat_id" in st.session_state:
            del st.session_state["current_chat_id"]
        if "chain" in st.session_state:
            del st.session_state["chain"]
        st.rerun()

    # Add search functionality
    search_term = container.text_input(
        "🔍 Buscar conversas", key="chat_search",
        placeholder="Busque por título ou data..."
    )

    container.divider()

    # Get all chats for current user
    chats = get_chat_list(st.session_state["user_id"])

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

            # Determine if this is the active chat
            is_active = st.session_state.get("current_chat_id") == chat_id
            
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

            # Create columns for the chat item
            col1, col2 = container.columns([0.85, 0.15])
            
            # Chat title and date
            with col1:
                if st.button(
                    f"{icon} {title}",
                    key=f"chat_{chat_id}",
                    use_container_width=True,
                    help=f"Criado em: {date_str}"
                ):
                    # Load the selected chat
                    chat_details = get_chat(chat_id)
                    _, _, _, _, _, file_type, file_path, file_url = chat_details

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

                # Small date label
                container.caption(date_str)

            # Delete button
            with col2:
                if st.button(
                    "🗑️",
                    key=f"del_{chat_id}",
                    help="Excluir esta conversa"
                ):
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

            # Add a subtle divider between chats
            container.markdown("---")

    # Add the "Sair" button at the bottom of the chat list
    if container.button("Sair", key="logout_button", use_container_width=True):
        # Clear all session state related to authentication
        for key in ["authenticated", "username", "user_id", "current_chat_id", "chain", "memoria"]:
            if key in st.session_state:
                del st.session_state[key]
        
        # Clear session cookies
        clear_session_cookies()
        st.rerun()


def file_upload_section(container):
    """Render the file upload section with dynamic inputs based on file type."""
    #container.markdown("### Carregar Documento")

    # Create a session state to track changes
    if "previous_tipo_arquivo" not in st.session_state:
        st.session_state["previous_tipo_arquivo"] = None

    # Select file type
    tipo_arquivo = container.selectbox(
        "Tipo de documento", TIPOS_ARQUIVOS_VALIDOS,
        help="Selecione o tipo de documento que deseja carregar"
    )

    # Check if file type changed
    file_type_changed = tipo_arquivo != st.session_state["previous_tipo_arquivo"]
    st.session_state["previous_tipo_arquivo"] = tipo_arquivo

    # Create unique keys for each input type to avoid conflicts
    arquivo = None
    if tipo_arquivo == "Site":
        arquivo = container.text_input(
            "URL do site", 
            placeholder="https://exemplo.com",
            key="site_input"
        )
    elif tipo_arquivo == "Youtube":
        arquivo = container.text_input(
            "URL do vídeo", 
            placeholder="https://youtube.com/watch?v=...",
            key="youtube_input"
        )
    elif tipo_arquivo == "Pdf":
        arquivo = container.file_uploader(
            "Arquivo PDF", type=["pdf"], 
            key="pdf_uploader",
            help="Faça upload de um arquivo PDF"
        )
    elif tipo_arquivo == "Csv":
        arquivo = container.file_uploader(
            "Arquivo CSV", type=["csv"], 
            key="csv_uploader",
            help="Faça upload de um arquivo CSV"
        )
    elif tipo_arquivo == "Txt":
        arquivo = container.file_uploader(
            "Arquivo TXT", type=["txt"], 
            key="txt_uploader",
            help="Faça upload de um arquivo TXT"
        )

    # Submit button with nice styling
    if container.button(
        "Carregar e Analisar", 
        use_container_width=True,
        disabled=not arquivo,
        key="submit_doc",
        help="Clique para carregar o documento e começar a conversa"
    ) and arquivo:
        with st.spinner("Processando documento..."):
            carrega_modelo(tipo_arquivo, arquivo)
        container.success("Documento carregado com sucesso!")
        st.rerun()

    return tipo_arquivo, arquivo

def main():
    # Configure the page with a wider layout
    st.set_page_config(
        page_title="DocGPT",
        layout="wide",
        initial_sidebar_state="expanded",
        page_icon="🤖"
    )
    
    # Inject custom CSS
    inject_custom_css()

    # Initialize the database
    init_database()

    # Check for logout action
    if st.query_params.get("logout"):
        # Clear all session state related to authentication
        for key in ["authenticated", "username", "user_id", "current_chat_id", "chain", "memoria"]:
            if key in st.session_state:
                del st.session_state[key]
        
        # Clear session cookies
        clear_session_cookies()
        
        # Remove the logout param and rerun
        st.query_params.clear()
        st.rerun()

    # Initialize session state variables if they don't exist
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    
    # First try to load session from cookie
    is_authenticated = load_session_from_cookie()
    
    # Debug info
    print(f"Session authentication status: {is_authenticated}")
    if is_authenticated:
        print(f"User ID: {st.session_state.get('user_id')}")
        print(f"Username: {st.session_state.get('username')}")

    # Check if user is authenticated
    if not is_authenticated:
        login_page()
    else:
        # Refresh the session cookie on each page load to extend its lifetime
        save_session_cookie(st.session_state["user_id"], st.session_state["username"])
        
        # Create a two-column layout
        left_col, right_col = st.columns([1, 3])

        with left_col:
            # Create a container for the file upload section
            with st.container():
                file_upload_section(st)

            st.divider()

            # Create a container for the chat list
            with st.container():
                render_chat_list(st)

        with right_col:
            # Display the chat interface
            pagina_chat()

   

if __name__ == "__main__":
    main()

