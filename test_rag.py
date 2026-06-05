import argparse
import os

from dotenv import load_dotenv

from rag_retriever import RAGRetriever


def main():
    parser = argparse.ArgumentParser(description="Test textbook retrieval for the adaptive tutor RAG layer.")
    parser.add_argument(
        "query",
        nargs="?",
        default="What is the main idea of the current source?",
        help="Question to retrieve relevant textbook chunks for.",
    )
    parser.add_argument(
        "--file",
        default="data/textbook/chapter_1.txt",
        help="Textbook/source file to index.",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=2,
        help="Number of chunks to retrieve.",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "MY_GEMINI_API_KEY":
        raise SystemExit("Set GEMINI_API_KEY in .env before testing RAG embeddings.")

    retriever = RAGRetriever(api_key=api_key)
    retriever.load_and_index_file(args.file)
    results = retriever.retrieve(args.query, k=args.k)

    if not results:
        raise SystemExit("No RAG results returned. Check your API key, source file, and terminal logs.")

    print(f"\nQuery: {args.query}\n")
    for index, result in enumerate(results, start=1):
        print(f"Result {index}: {result['title']} | score={result['score']:.4f}")
        print(result["text"])
        print("-" * 80)


if __name__ == "__main__":
    main()
