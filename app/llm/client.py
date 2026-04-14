from app.llm.qwen_client import QwenClient

# Единственный инстанс клиента на всё приложение.
# При смене провайдера меняется только эта строка.
llm_client = QwenClient()
