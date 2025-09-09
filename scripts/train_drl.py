"""
Script to train the DRL model for hospital routing.
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

import logging
from datetime import datetime
from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardThreshold
from database.models import get_session, Hospital
from routing.mapbox_router import MapboxRouter
from routing.drl_environment import HospitalRoutingEnv, DRLRouter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def train_drl_model(
    total_timesteps: int = 100000,
    learning_rate: float = 0.0003,
    batch_size: int = 64,
    gamma: float = 0.99,
    tensorboard_log: str = "./logs/drl"
):
    """
    Train the DRL model for hospital routing.
    
    Args:
        total_timesteps: Total number of timesteps to train for
        learning_rate: Learning rate for the optimizer
        batch_size: Minibatch size for training
        gamma: Discount factor
        tensorboard_log: Directory to save TensorBoard logs
    """
    logger.info("Starting DRL model training...")
    
    # Initialize database session
    session = get_session()
    
    try:
        # Get all hospitals
        hospitals = session.query(Hospital).all()
        if not hospitals:
            logger.warning("No hospitals found in the database. Loading sample data...")
            from database.models import create_sample_data
            create_sample_data(session)
            hospitals = session.query(Hospital).all()
        
        logger.info(f"Found {len(hospitals)} hospitals in the database")
        
        # Initialize Mapbox router
        mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN")
        if not mapbox_token:
            raise ValueError("MAPBOX_ACCESS_TOKEN environment variable not set")
            
        router = MapboxRouter(mapbox_token)
        
        # Create environment
        env = HospitalRoutingEnv(hospitals, router)
        
        # Create model directory if it doesn't exist
        os.makedirs("models", exist_ok=True)
        
        # Create DRL router
        model_path = "models/hospital_router"
        drl_router = DRLRouter(env, model_path=f"{model_path}.zip")
        
        # Setup callbacks
        eval_callback = EvalCallback(
            env,
            best_model_save_path="./models/best/",
            log_path="./logs/eval/",
            eval_freq=1000,
            deterministic=True,
            render=False
        )
        
        # Train the model
        logger.info("Starting training...")
        drl_router.train(
            total_timesteps=total_timesteps,
            learning_rate=learning_rate,
            batch_size=batch_size,
            gamma=gamma,
            tensorboard_log=tensorboard_log
        )
        
        logger.info(f"Training completed. Model saved to {model_path}")
        
    except Exception as e:
        logger.error(f"Error during training: {e}", exc_info=True)
        raise
    
    finally:
        session.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Train DRL model for hospital routing")
    parser.add_argument("--timesteps", type=int, default=100000, 
                       help="Total number of timesteps to train for")
    parser.add_argument("--lr", type=float, default=0.0003, 
                       help="Learning rate")
    parser.add_argument("--batch-size", type=int, default=64, 
                       help="Minibatch size")
    parser.add_argument("--gamma", type=float, default=0.99, 
                       help="Discount factor")
    parser.add_argument("--log-dir", type=str, default="./logs/drl", 
                       help="Directory to save TensorBoard logs")
    
    args = parser.parse_args()
    
    train_drl_model(
        total_timesteps=args.timesteps,
        learning_rate=args.lr,
        batch_size=args.batch_size,
        gamma=args.gamma,
        tensorboard_log=args.log_dir
    )
