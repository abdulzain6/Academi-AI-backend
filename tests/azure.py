from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain.schema import HumanMessage


emb = AzureOpenAIEmbeddings(
    azure_endpoint="https://academi-app.openai.azure.com/",
    api_version="2023-05-15",
    azure_deployment="text-embedding-3-small",
    api_key=""   
)

print(emb.embed_query(
    "hi"
))