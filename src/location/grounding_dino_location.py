import torch
from PIL import Image, ImageDraw, ImageFont
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
import os
import re
import time
import json

class GroundingDinoLocator:
    """
    A class to locate objects in an image using the Grounding Dino model.
    """

    STR_PREFIX = "[LOCATION | GDINO]"

    def __init__(
            self,
            grounding_dino_model_id: str = "IDEA-Research/grounding-dino-base",
            input_image_name: str = "input_image.jpg",
            score_threshold: float = 0.3,
            save_file_json: bool = True,
            save_file_jpg: bool = True
    ):
        """
        TODO
        """

        print(f"\n{self.STR_PREFIX} Initializing Grounding DINO object locator...\n")

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.score_threshold = score_threshold
        self.save_file_json = save_file_json
        self.save_file_jpg = save_file_jpg

        # Load the processor and model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = AutoProcessor.from_pretrained(grounding_dino_model_id)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(grounding_dino_model_id).to(device)

        # Input image path
        input_image_path = os.path.join(
            self.script_dir, 
            "..",                
            "input_images",
            input_image_name
        )

        # Load input image
        if os.path.isfile(input_image_path):
            self.input_image = Image.open(input_image_path)
        else:
            raise FileNotFoundError(f"{self.STR_PREFIX} The image {input_image_name} was not found at {input_image_path}.\n")
        
        # Input tags directory path
        input_tags_dir = os.path.join(
            self.script_dir, 
            "..",
            "tagging",
            "output_tags"
        )

        # Load tags from the most recent .json file in input_tags_dir
        self.input_tags, tags_filename = self.read_input_tags(input_tags_dir=input_tags_dir)

        # Print input information
        print(f"{self.STR_PREFIX} Input image filename: {input_image_path}\n")
        print(f"{self.STR_PREFIX} Input tags filename: {input_tags_dir}/{tags_filename}\n")

        # Output location directory path
        output_location_dir = os.path.join(
            self.script_dir, 
            "output_location"
        )

        if save_file_json or save_file_jpg:
            # Create the output directory if it does not exist
            os.makedirs(output_location_dir, exist_ok=True)
            
            # Prepare timestamped output file
            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")

            if save_file_json:
                # Prepare JSON output file
                output_filename_json = f"location_gdino_{timestamp}.json"
                self.output_file_json = os.path.join(output_location_dir, output_filename_json)
            if save_file_jpg:
                # Prepare JPG output file
                output_filename_jpg = f"location_gdino_{timestamp}.jpg"
                self.output_file_jpg = os.path.join(output_location_dir, output_filename_jpg)

    def read_input_tags(self, input_tags_dir: str) -> tuple[dict, str]:
        """
        Reads the tags from the most recent .json file in the tags directory.

        Returns:
            tuple[str, str]: A tuple containing the content of the file as a dictionary and the filename.
        """
        # Gather all .json files in input_tags_dir
        json_files = [
            os.path.join(input_tags_dir, f)
            for f in os.listdir(input_tags_dir)
            if f.endswith(".json")
        ]
        if not json_files:
            raise FileNotFoundError(f"{self.STR_PREFIX} No .json files found in {input_tags_dir}\n")

        # Select the most recently modified .json file
        latest_json_path = max(json_files, key=os.path.getmtime)
        
        # Extract the filename (without the full path)
        filename = os.path.basename(latest_json_path)
        
        # Read the content of the file
        with open(latest_json_path, "r", encoding="utf-8") as f:
            tags_content = json.load(f)  # Cargar el contenido como un diccionario
        
        # Return a tuple of (content, filename)
        return tags_content, filename
    
    def json_to_gdino_prompt(self, tags: dict) -> str:
        """
        Converts the tags dictionary to a Grounding DINO prompt.
        """
        # Extract the tags from the dictionary
        tags_list = [tag for tag in tags.values()]
        
        # Build the Grounding Dino prompt
        prompt = ". ".join(tags_list) + "."

        return prompt
    
    def gdino_results_to_json(self, results: dict) -> dict:
        """
        Converts the Grounding DINO results to a JSON dict.
        """
        scores = results.get("scores", torch.tensor([])).tolist()
        boxes = results.get("boxes", torch.tensor([])).tolist()
        labels = results.get("labels", [])
                
        result = []
        for label, bbox, score in zip(labels, boxes, scores):
            obj = {
                "label": label,
                "score": float(score),
                "bbox": {
                    "x_min": bbox[0],
                    "y_min": bbox[1],
                    "x_max": bbox[2],
                    "y_max": bbox[3]
                }
            }
            result.append(obj)
        
        return result
    
    def filter_confidence(self, results: dict, threshold: float) -> dict:
        """
        Filters the results based on the confidence threshold.
        """
        filtered_results = [result for result in results if result["score"] > threshold]
        return filtered_results
    
    def draw_bounding_boxes(self, results: dict) -> Image:
        """
        Draws bounding boxes around the detected objects in the image.
        """    
        image = self.input_image.copy()
        draw = ImageDraw.Draw(image)        
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)

        # Draw bounding boxes for each detected object
        for obj in results:
            label = obj.get("label", "unknown")
            score = obj.get("score", 0.0)
            bbox = obj.get("bbox", {})
            
            # Extract bounding box coordinates
            x_min = int(bbox.get("x_min", 0))
            y_min = int(bbox.get("y_min", 0))
            x_max = int(bbox.get("x_max", 0))
            y_max = int(bbox.get("y_max", 0))
            
            # Draw the bounding box
            draw.rectangle([x_min, y_min, x_max, y_max], outline="red", width=3)
            
            # Draw the label and score
            text = f"{label}: {score:.2f}"
            draw.text((x_min, y_min - 20), text, fill="red", font=font)

        return image
    
    def locate_objects(self, input_tags: str) -> dict:
        """
        TODO
        """
        # Convert the tags JSON text to a Grounding Dino prompt
        text = self.json_to_gdino_prompt(input_tags)

        # Process and predict
        inputs = self.processor(images=self.input_image, text=text, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        results = self.processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            target_sizes=[self.input_image.size[::-1]]
        )[0]

        print(f"{self.STR_PREFIX} Object detection results:\n{results}\n")

        # Convert the results to JSON format
        results_json = self.gdino_results_to_json(results)

        # Filter the results based on the confidence threshold
        results_json = self.filter_confidence(results_json, threshold=self.score_threshold)

        print(f"{self.STR_PREFIX} JSON results:\n{json.dumps(results_json, indent=4)}\n")
        
        if self.save_file_json:
            # Save the results to a JSON file
            with open(self.output_file_json, "w", encoding="utf-8") as f:
                json.dump(results_json, f, indent=4)
                print(f"{self.STR_PREFIX} Text results saved to: {self.output_file_json}\n")

        if self.save_file_jpg:
            # Draw bounding boxes around the detected objects
            results_image = self.draw_bounding_boxes(results_json)

            # Save the image with bounding boxes
            results_image.save(self.output_file_jpg)
            print(f"{self.STR_PREFIX} Bounding box location image saved to: {self.output_file_jpg}")

        return results_json

def main():
    """
    Main function for the Grounding DINO Locator.
    """
    locator = GroundingDinoLocator(input_image_name="desk.jpg")
    locator.locate_objects(locator.input_tags)


if __name__ == "__main__":
    main()