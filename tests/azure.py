from langchain_openai import AzureChatOpenAI
from langchain.schema import HumanMessage

llm = AzureChatOpenAI(
    azure_deployment="gpt-4o-mini",
    api_version="2024-08-01-preview",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    azure_endpoint="https://academi-app.openai.azure.com/",
    api_key="B3g2ajP77zRSGcpLUjSaIutqSXqefY2YSL08v3C3BMAeGZa8ZYYZJQQJ99AKACYeBjFXJ3w3AAABACOGlfjx"
)

"B3g2ajP77zRSGcpLUjSaIutqSXqefY2YSL08v3C3BMAeGZa8ZYYZJQQJ99AKACYeBjFXJ3w3AAABACOGlfjx"
print(llm.invoke(
    [HumanMessage(content="Hi")]
))