import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, Message
import requests
import json
import time
import re
from typing import Optional, List, Dict, Any
from telegraph import Telegraph
import html

TELEGRAM_TOKEN = '7715356843:AAGFZj3oRXmDi_fNwwYPQk82RPahfU6Ijcs'
TUNE_API_KEY = 'sk-tune-7OZErMk8lQxFzO2m6cVX6zy4CwJmNuLb4dn'
TUNE_API_URL = 'https://proxy.tune.app/chat/completions'

bot = telebot.TeleBot(TELEGRAM_TOKEN)

conversations: Dict[int, Dict] = {}

MODEL_MAP = {
    'gpt-4o-mini': {'display_name': 'GPT-4o-Mini', 'identifier': 'openai/gpt-4o-mini', 'supports_images': True},
    'claude': {'display_name': 'Claude 3.5 Sonnet', 'identifier': 'anthropic/claude-3.5-sonnet', 'supports_images': True},
    'gpt4o': {'display_name': 'GPT-4o', 'identifier': 'rohan/tune-gpt-4o', 'supports_images': True},
    'mistral': {'display_name': 'Mistrал Large 2', 'identifier': 'rohan/mistral-large-2', 'supports_images': False},
    'gpt-o1-mini': {'display_name': 'GPT-o1-mini', 'identifier': 'openai/o1-mini', 'supports_images': False},
    'gpt-o1-preview': {'display_name': 'GPT-o1-preview', 'identifier': 'openai/o1-preview', 'supports_images': False},
}

MENU_COMMANDS = {
    '🤖 Выбрать модель': 'select_model',
    '🗑 Очистить диалог': 'clear_dialog'
}

def format_text_for_telegraph(text: str) -> str:
    # Convert markdown to HTML for Telegraph
    # Headers
    text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    
    # Bold and Italic
    text = re.sub(r'\*\*\*(.*?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    
    # Code blocks
    text = re.sub(r'```(.*?)```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    
    # Lists
    text = re.sub(r'^\* (.*?)$', r'<ul><li>\1</li></ul>', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\. (.*?)$', r'<ol><li>\1</li></ol>', text, flags=re.MULTILINE)
    
    # Quotes
    text = re.sub(r'^> (.*?)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)
    
    # Links
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    
    # Paragraphs
    paragraphs = text.split('\n\n')
    text = ''.join([f'<p>{p}</p>' if not any(p.startswith(tag) for tag in ['<h', '<ul', '<ol', '<blockquote', '<pre']) 
                    else p for p in paragraphs])
    
    return text

def get_model_identifier(model_name: str) -> str:
    return MODEL_MAP.get(model_name, {}).get('identifier', model_name)

def model_supports_images(model_name: str) -> bool:
    return MODEL_MAP.get(model_name, {}).get('supports_images', False)

def get_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add(*[KeyboardButton(text) for text in MENU_COMMANDS.keys()])
    return keyboard

def get_model_selection_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [KeyboardButton(MODEL_MAP[model_key]['display_name']) for model_key in MODEL_MAP]
    keyboard.add(*buttons)
    keyboard.add(KeyboardButton('⬅ Назад'))
    return keyboard

def create_telegraph_page(title: str, content: str) -> str:
    telegraph = Telegraph()
    telegraph.create_account(short_name='TelegramBot')
    
    # Format content for Telegraph
    formatted_content = format_text_for_telegraph(content)
    
    response = telegraph.create_page(
        title=title,
        html_content=formatted_content,
        author_name='AI Assistant'
    )
    return f"https://telegra.ph/{response['path']}"

def generate_text(prompt: str, history: List[Dict], images_data: List[str], model_name: str):
    model_identifier = get_model_identifier(model_name)
    is_streaming = model_name not in ['gpt-o1-mini', 'gpt-o1-preview']
    
    api_messages = []
    for msg in history:
        content_blocks = [{'type': 'text', 'text': msg['content']}]
        if msg.get('images_data') and model_supports_images(model_name):
            for image_url in msg['images_data']:
                content_blocks.append({'type': 'image_url', 'image_url': {'url': image_url}})
        api_messages.append({'role': msg['role'], 'content': content_blocks})

    content_blocks = [{'type': 'text', 'text': prompt}]
    if images_data and model_supports_images(model_name):
        for image_url in images_data:
            content_blocks.append({'type': 'image_url', 'image_url': {'url': image_url}})
    api_messages.append({'role': 'user', 'content': content_blocks})

    headers = {
        'Authorization': f'Bearer {TUNE_API_KEY}',
        'Content-Type': 'application/json',
    }
    
    data = {
        'messages': api_messages,
        'model': model_identifier,
        'max_tokens': 8192,
        'temperature': 0.7,
        'stream': is_streaming,
    }

    try:
        response = requests.post(TUNE_API_URL, headers=headers, json=data, stream=is_streaming)
        response.raise_for_status()
        return response.iter_lines() if is_streaming else response.json()
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None

def format_telegram_message(text: str) -> str:
    # Format text for Telegram HTML parsing mode
    text = html.escape(text)  # Escape HTML special characters
    
    # Apply formatting
    text = re.sub(r'\*\*\*(.*?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
    
    return text

@bot.message_handler(commands=['start'])
def send_welcome(message: Message):
    models_list = "\n".join([f"• {info['display_name']}" for info in MODEL_MAP.values()])
    welcome_message = f"""Привет! Я бот для общения с различными языковыми моделями.

Доступные модели:
{models_list}"""
    
    bot.reply_to(message, welcome_message, reply_markup=get_menu_keyboard())

@bot.message_handler(func=lambda message: message.text in MENU_COMMANDS.keys())
def handle_menu_commands(message: Message):
    command = MENU_COMMANDS[message.text]
    user_id = message.chat.id

    if command == 'select_model':
        bot.send_message(
            user_id,
            "Выберите модель для общения:",
            reply_markup=get_model_selection_keyboard()
        )
    elif command == 'clear_dialog':
        if user_id in conversations:
            conversations[user_id]['history'] = []
            bot.send_message(
                user_id,
                "Диалог очищен. Можете начать новый разговор.",
                reply_markup=get_menu_keyboard()
            )

@bot.message_handler(func=lambda message: message.text == '⬅ Назад')
def handle_back(message: Message):
    bot.send_message(
        message.chat.id,
        "Главное меню:",
        reply_markup=get_menu_keyboard()
    )

@bot.message_handler(func=lambda message: message.text in [model['display_name'] for model in MODEL_MAP.values()])
def handle_model_selection(message: Message):
    user_id = message.chat.id
    selected_model = next(
        (model_key for model_key, model_info in MODEL_MAP.items()
         if model_info['display_name'] == message.text),
        None
    )

    if selected_model:
        conversations.setdefault(user_id, {})['model'] = selected_model
        conversations[user_id]['history'] = []
        bot.send_message(
            user_id,
            f"Модель изменена на {message.text}. Можете начать диалог.",
            reply_markup=get_menu_keyboard()
        )

@bot.message_handler(content_types=['text', 'photo'])
def handle_messages(message: Message):
    user_id = message.chat.id

    if message.text in MENU_COMMANDS.keys() or message.text == '⬅ Назад':
        return

    if user_id not in conversations or 'model' not in conversations[user_id]:
        bot.reply_to(
            message,
            "Пожалуйста, сначала выберите модель через меню.",
            reply_markup=get_menu_keyboard()
        )
        return

    conversation = conversations[user_id]
    images_data = []

    if message.photo and model_supports_images(conversation['model']):
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        image_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        images_data.append(image_url)

    model_name = conversation['model']
    message_text = message.text or message.caption or ""

    bot.send_chat_action(user_id, 'typing')

    response_data = generate_text(message_text, conversation['history'], images_data, model_name)
    if response_data is None:
        bot.reply_to(
            message,
            "Произошла ошибка при обращении к модели.",
            reply_markup=get_menu_keyboard()
        )
        return

    user_message = {'role': 'user', 'content': message_text}
    if images_data:
        user_message['images_data'] = images_data
    conversation['history'].append(user_message)

    if isinstance(response_data, dict):
        assistant_message = response_data['choices'][0]['message']['content']
        conversation['history'].append({'role': 'assistant', 'content': assistant_message})
        
        # Create Telegraph page for long messages
        if len(assistant_message) > 100:
            telegraph_url = create_telegraph_page("Bot Response", assistant_message)
            formatted_message = f"Ответ превысил 100 символов. Прочитать полный ответ можно здесь: {telegraph_url}"
        else:
            formatted_message = format_telegram_message(assistant_message)
        
        bot.reply_to(message, formatted_message, parse_mode='HTML')
    else:
        assistant_message = ''
        temp_message = None
        last_update_time = 0

        for line in response_data:
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    json_data = decoded_line[6:]
                    if json_data.strip() == '[DONE]':
                        break
                    
                    try:
                        data = json.loads(json_data)
                        delta_content = data['choices'][0]['delta'].get('content', '')

                        if delta_content:
                            assistant_message += delta_content
                            current_time = time.time()

                            if temp_message is None and assistant_message.strip():
                                if len(assistant_message) > 100:
                                    temp_message = bot.reply_to(message, "Генерация ответа...")
                                else:
                                    formatted_message = format_telegram_message(assistant_message)
                                    temp_message = bot.reply_to(message, formatted_message, parse_mode='HTML')
                                last_update_time = current_time
                            elif temp_message and current_time - last_update_time >= 1.0:
                                try:
                                    if len(assistant_message) > 100:
                                        bot.edit_message_text(
                                            "Генерация ответа...",
                                            chat_id=user_id,
                                            message_id=temp_message.message_id
                                        )
                                    else:
                                        formatted_message = format_telegram_message(assistant_message)
                                        bot.edit_message_text(
                                            formatted_message,
                                            chat_id=user_id,
                                            message_id=temp_message.message_id,
                                            parse_mode='HTML'
                                        )
                                    last_update_time = current_time
                                except telebot.apihelper.ApiTelegramException:
                                    continue
                    except json.JSONDecodeError:
                        continue

        if temp_message and assistant_message.strip():
            try:
                if len(assistant_message) > 100:
                    telegraph_url = create_telegraph_page("Bot Response", assistant_message)
                    bot.edit_message_text(
                        f"Ответ превысил 100 символов. Прочитать полный ответ можно здесь: {telegraph_url}",
                        chat_id=user_id,
                        message_id=temp_message.message_id
                    )
                else:
                    formatted_message = format_telegram_message(assistant_message)
                    bot.edit_message_text(
                        formatted_message,
                        chat_id=user_id,
                        message_id=temp_message.message_id,
                        parse_mode='HTML'
                    )
            except telebot.apihelper.ApiTelegramException:
                pass

        conversation['history'].append({'role': 'assistant', 'content': assistant_message})

def main():
    print("Bot is running...")
    bot.infinity_polling()

if __name__ == '__main__':
    main()