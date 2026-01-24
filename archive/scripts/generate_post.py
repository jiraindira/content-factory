print(">>> generate_post.py started")

from agents.topic_agent import TopicSelectionAgent
from schemas.topic import TopicInput
from datetime import date

def main():
    agent = TopicSelectionAgent()
    
    # Prepare input data
    input_data = TopicInput(
        current_date=date.today().isoformat(),
        region="US"
    )
    
    # Run the agent
    try:
        output = agent.run(input_data)
        # Pydantic v2: use model_dump_json instead of .json()
        print(output.model_dump_json(indent=2))
    except Exception as e:
        print("Error running agent:", e)

if __name__ == "__main__":
    main()
