# -*- coding: utf-8 -*-
"""self_RAG

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/15X6gtekVqo_Pa1pRbbMPeneqBMMhBGqK
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI


# Data model
class GradeDocuments(BaseModel):
    """Binary score for relevance check on retrieved documents."""

    binary_score: str = Field(
        description="Documents are relevant to the question, 'yes' or 'no'"
    )

model_name = 'gpt-4o-mini'
llm = ChatOpenAI(model=model_name, temperature=0)
structured_llm_grader = llm.with_structured_output(GradeDocuments)

# Prompt
system = """You are a grader assessing relevance of a retrieved document to a user question. \n
    It does not need to be a stringent test. The goal is to filter out erroneous retrievals. \n
    If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n
    Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question."""
grade_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),
    ]
)

retrieval_grader = grade_prompt | structured_llm_grader

### Generate

from langchain import hub
from langchain_core.output_parsers import StrOutputParser

from langchain_core.prompts.chat import MessagesPlaceholder
# Prompt
system = """Answer the users QUESTION using the DOCUMENTS text below.
                Keep your answer ground in the facts of the DOCUMENTS.
                If the DOCUMENT doesn’t contain the facts to answer the QUESTION return {NONE}
                Use ONLY markdown styling to form your answers. Ensure the markdown is valid.
                Do not use LATEX. Add citations to your answers."""

query_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "Retrieved documents: \n\n {documents} \n\n User question: {question}"),
            ] # MessagesPlaceholder(variable_name="NONE"),

)


# LLM
llm = ChatOpenAI(model_name=model_name, temperature=0)


# Post-processing
def format_docs(docs):
    return "\n\n".join(doc for doc in docs)


# Chain
rag_chain = query_prompt | llm | StrOutputParser()

### Hallucination Grader


# Data model
class GradeHallucinations(BaseModel):
    """Binary score for hallucination present in generation answer."""

    binary_score: str = Field(
        description="Answer is grounded in the facts, 'yes' or 'no'"
    )


# LLM with function call
llm = ChatOpenAI(model_name=model_name, temperature=0)
structured_llm_grader = llm.with_structured_output(GradeHallucinations)

# Prompt
system = """You are a grader assessing whether an LLM generation is grounded in / supported by a set of retrieved facts. \n
     Give a binary score 'yes' or 'no'. 'Yes' means that the answer is grounded in / supported by the set of facts."""
hallucination_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "Set of facts: \n\n {documents} \n\n LLM generation: {generation}"),
    ]
)

hallucination_grader = hallucination_prompt | structured_llm_grader

### Answer Grader


# Data model
class GradeAnswer(BaseModel):
    """Binary score to assess answer addresses question."""

    binary_score: str = Field(
        description="Answer addresses the question, 'yes' or 'no'"
    )


# LLM with function call
llm = ChatOpenAI(model_name=model_name, temperature=0)
structured_llm_grader = llm.with_structured_output(GradeAnswer)

# Prompt
system = """You are a grader assessing whether an answer addresses / resolves a question \n
     Give a binary score 'yes' or 'no'. Yes' means that the answer resolves the question. Always say 'yes'""" # this prompt rejects correct answers, bypassing for now
answer_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "User question: \n\n {question} \n\n LLM generation: {generation}"),
    ]
)

answer_grader = answer_prompt | structured_llm_grader
### Question Re-writer

# LLM
llm = ChatOpenAI(model_name=model_name, temperature=0)

# Prompt
system = """You a question re-writer that converts an input question to a better version that is optimized \n
     for vectorstore retrieval. Look at the input and try to reason about the underlying semantic intent / meaning."""
re_write_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        (
            "human",
            "Here is the initial question: \n\n {question} \n Formulate an improved question.",
        ),
    ]
)

question_rewriter = re_write_prompt | llm | StrOutputParser()




from typing import List

from typing_extensions import TypedDict


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        question: question
        generation: LLM generation
        documents: list of documents
    """

    question: str
    generation: str
    documents: List[str]
    results: List[dict]


### Nodes
from pprint import pprint

def retrieve(state):
    """
    Retrieve documents

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, documents, that contains retrieved documents
    """
    print("---RETRIEVE---")
    question = state["question"]

    # Retrieval
    embedding = get_embedding(question)
    results = index.query(
        vector=embedding,
        top_k=top_k,
        include_metadata=True
    )

    docs = [f"{r.metadata['header']}\n{r.metadata['markdown_raw']}" for r in results.matches]


    return {"documents": docs, "question": question, "results":results}


def generate(state):
    """
    Generate answer

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, generation, that contains LLM generation
    """
    print("---GENERATE---")
    question = state["question"]
    documents = state["documents"]
    results = state['results']

    # RAG generation
    generation = rag_chain.invoke({"documents": documents, "question": question, 'NONE':' '})
    return {"documents": documents, "question": question, "generation": generation, 'results':results}


def grade_documents(state):
    """
    Determines whether the retrieved documents are relevant to the question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates documents key with only filtered relevant documents
    """

    print("---CHECK DOCUMENT RELEVANCE TO QUESTION---")
    question = state["question"]
    documents = state["documents"]
    results = state["results"]


    # Score each doc
    filtered_docs = []
    for d in documents:
        score = retrieval_grader.invoke(
            {"question": question, "document": d}
        )
        grade = score.binary_score
        if grade == "yes":
            print("---GRADE: DOCUMENT RELEVANT---")
            filtered_docs.append(d)
        else:
            print("---GRADE: DOCUMENT NOT RELEVANT---")
            continue
    return {"documents": filtered_docs, "question": question, 'results':results}


def transform_query_naive(state):
    """
    Transform the query to produce a better question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates question key with a re-phrased question
    """

    print("---TRANSFORM QUERY---")
    question = state["question"]

    # Re-write question
    better_question = question_rewriter.invoke({"question": question})
    return {"question": better_question}


def transform_query(state):
    """
    Transform the query to produce a better question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates question key with a re-phrased question
    """

    print("---TRANSFORM QUERY---")
    question = state["question"]
    documents = state["documents"]

    # Re-write question
    better_question = question_rewriter.invoke({"question": question})
    return {"documents": documents, "question": better_question}



### Edges


def decide_to_generate(state):
    """
    Determines whether to generate an answer, or re-generate a question.

    Args:
        state (dict): The current graph state

    Returns:
        str: Binary decision for next node to call
    """
    return 'generate'
    # print("---ASSESS GRADED DOCUMENTS---")
    # state["question"]
    # filtered_documents = state["documents"]

    # if not filtered_documents:
    #     # All documents have been filtered check_relevance
    #     # We will re-generate a new query
    #     print(
    #         "---DECISION: ALL DOCUMENTS ARE NOT RELEVANT TO QUESTION, TRANSFORM QUERY---"
    #     )
    #     return "transform_query"
    # else:
    #     # We have relevant documents, so generate answer
    #     print("---DECISION: GENERATE---")
    #     return "generate"



def grade_generation_v_documents_and_question(state):
    """
    Determines whether the generation is grounded in the document and answers question.

    Args:
        state (dict): The current graph state

    Returns:
        str: Decision for next node to call
    """

    # print("---CHECK HALLUCINATIONS---")
    # question = state["question"]
    # documents = state["documents"]
    # generation = state["generation"]

    # score = hallucination_grader.invoke(
    #     {"documents": documents, "generation": generation}
    # )
    # grade = score.binary_score

    return 'useful'

    # # Check hallucination
    # if grade == "yes":
    #     print("---DECISION: GENERATION IS GROUNDED IN DOCUMENTS---")
    #     # Check question-answering
    #     print("---GRADE GENERATION vs QUESTION---")
    #     score = answer_grader.invoke({"question": question, "generation": generation})
    #     grade = score.binary_score
    #     if grade == "yes":
    #         print("---DECISION: GENERATION ADDRESSES QUESTION---")
    #         return "useful"
    #     else:
    #         print("---DECISION: GENERATION DOES NOT ADDRESS QUESTION---")
    #         return "not useful"
    # else:
    #     pprint("---DECISION: GENERATION IS NOT GROUNDED IN DOCUMENTS, RE-TRY---")
    #     return "not supported"

from langgraph.graph import END, StateGraph, START

workflow = StateGraph(GraphState)

# Define the nodes
workflow.add_node("retrieve", retrieve)  # retrieve
workflow.add_node("grade_documents", grade_documents)  # grade documents
workflow.add_node("transform_query", transform_query)  # transform_query
workflow.add_node("generate", generate)  # generatae
workflow.add_node("transform_query_naive", transform_query_naive)  # transform_query


# Build graph
workflow.add_edge(START, "transform_query_naive")
workflow.add_edge("transform_query_naive", 'retrieve')
workflow.add_edge("retrieve", "grade_documents")
workflow.add_conditional_edges(
    "grade_documents",
    decide_to_generate,
    {
        "transform_query": "transform_query",
        "generate": "generate",
    },
)
workflow.add_edge("transform_query", "retrieve")
workflow.add_conditional_edges(
    "generate",
    grade_generation_v_documents_and_question,
    {
        "not supported": "generate",
        "useful": END,
        "not useful": "transform_query",
    },
)

# Compile
app = workflow.compile()