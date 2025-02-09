import sys
import os
from pathlib import Path

# Add the parent directory to system path before other imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import streamlit as st
import pandas as pd
from catboost import CatBoostClassifier, Pool
from preprocess import DataPreprocessor


class StreamlitApp:
    def __init__(self):
        st.set_page_config(
            page_title="DSiP Prediction App",
            page_icon="🎯",
            layout="wide"
        )
        # Load the CatBoost model at startup
        try:
            self.model = CatBoostClassifier()
            self.model.load_model("models/catboost_model.cbm")
            # Get feature names from the model
            self.feature_names = self.model.feature_names_
            st.sidebar.success("Model loaded successfully!")
            st.sidebar.write("Model features:", self.feature_names)
        except Exception as e:
            st.sidebar.error(f"Error loading model: {str(e)}")

    def ensure_column_order(self, df):
        """Ensure columns are in the correct order based on model's feature names"""
        if not hasattr(self, 'feature_names') or not self.feature_names:
            raise ValueError("Model feature names not available")

        # Create a new DataFrame with columns in the correct order
        ordered_df = pd.DataFrame()

        # Add columns in the order expected by the model
        for feature in self.feature_names:
            if feature in df.columns:
                ordered_df[feature] = df[feature]
            else:
                st.warning(f"Missing feature: {feature}")
                # Add a placeholder column if needed
                ordered_df[feature] = "missing"

        return ordered_df

    def prepare_categorical_features(self, df, cat_features):
        """Prepare categorical features for CatBoost"""
        df = df.copy()

        # First ensure correct column order
        df = self.ensure_column_order(df)

        # Get categorical feature indices based on model's feature names
        cat_indices = []
        for i, feature in enumerate(self.feature_names):
            if feature in cat_features:
                cat_indices.append(i)
                # Convert to string
                df[feature] = df[feature].astype(str)

        # Display debug information
        st.write("Feature names from model:", self.feature_names)
        st.write("Actual columns in data:", df.columns.tolist())
        st.write("Categorical feature indices:", cat_indices)

        return df, cat_indices

    def preprocess_test_data(self, df):
        """Preprocess test data using the preprocessor"""
        try:
            # Initialize preprocessor
            preprocessor = DataPreprocessor(
                output_path=Path("data/processed"),
                remove_outliers=False,
                fillna=True,
                save_as_pickle=False
            )

            # Process the test data
            processed_df = preprocessor.preprocess_test(df_test=df)

            return processed_df

        except Exception as e:
            st.error(f"Error in preprocessing: {str(e)}")
            raise

    def home_page(self):
        """Home page with prediction functionality"""
        st.title("🎯 Click Prediction Model")
        st.write("""
        Upload your test data file to get click predictions.

        The file should be a CSV containing the required features for prediction.
        """)

        uploaded_file = st.file_uploader("Upload test data (CSV)", type=['csv'])

        if uploaded_file is not None:
            try:
                # Read the uploaded file
                df = pd.read_csv(uploaded_file)

                # Show data preview
                st.subheader("Data Preview")
                st.write(df.head())
                st.write("Data shape:", df.shape)
                st.write("Original columns:", df.columns.tolist())

                if st.button("Generate Predictions"):
                    with st.spinner("Preprocessing data and generating predictions..."):
                        try:
                            # Preprocess the test data
                            processed_df = self.preprocess_test_data(df)

                            # Get categorical features
                            cat_features = processed_df.select_dtypes(include=['object', 'category']).columns.tolist()

                            # Prepare categorical features and ensure column order
                            processed_df, cat_indices = self.prepare_categorical_features(processed_df, cat_features)

                            # Create CatBoost Pool
                            st.write("Creating prediction pool...")
                            st.write("Categorical features:", cat_features)
                            st.write("Final column order:", processed_df.columns.tolist())

                            # Create pool with categorical feature indices
                            test_pool = Pool(
                                data=processed_df,
                                cat_features=cat_indices  # Use indices instead of names
                            )

                            # Generate predictions
                            predictions = self.model.predict_proba(test_pool)[:, 1]

                            # Create DataFrame with predictions
                            predictions_df = pd.DataFrame(predictions)

                            # Save predictions without header and index
                            predictions_csv = predictions_df.to_csv(index=False, header=False)

                            # Display predictions preview
                            st.subheader("Predictions Preview (First 5 rows)")
                            st.write(predictions_df.head())

                            # Add download button
                            st.download_button(
                                label="Download Predictions",
                                data=predictions_csv,
                                file_name="predictions.csv",
                                mime="text/csv"
                            )

                            # Show prediction statistics
                            st.subheader("Prediction Statistics")
                            st.write(f"Number of predictions: {len(predictions)}")
                            st.write(f"Mean prediction score: {predictions.mean():.4f}")
                            st.write(f"Prediction range: {predictions.min():.4f} to {predictions.max():.4f}")

                            # Distribution plot
                            st.subheader("Prediction Distribution")
                            hist_data = pd.DataFrame(predictions, columns=['Probability'])
                            st.bar_chart(hist_data.Probability.value_counts(bins=10).sort_index())

                        except Exception as e:
                            st.error(f"Error generating predictions: {str(e)}")
                            st.error("Debug info:")
                            st.write("Model type:", type(self.model))
                            if 'processed_df' in locals():
                                st.write("Processed data shape:", processed_df.shape)
                                st.write("Processed data columns:", processed_df.columns.tolist())
                                st.write("Data types:", processed_df.dtypes)
                                st.write("Categorical features:", cat_features)
                                st.write("Feature names from model:", self.feature_names)
                            raise

            except Exception as e:
                st.error(f"Error reading file: {str(e)}")
                raise

    def run(self):
        """Run the Streamlit app"""
        self.home_page()


if __name__ == "__main__":
    app = StreamlitApp()
    app.run()