import boto3
import json
import os
import time
import uuid

class ai_util:

    def __init__(self):
        self.transcribe = boto3.client("transcribe")
        self.bedrock = boto3.client("bedrock-runtime")
        self.s3 = boto3.client("s3")
        self.meeting_summary_store = os.environ['TRANSCRIBE_BUCKET']
        self.meeting_recordings_store = os.environ['STORAGE_BUCKET']

    def meeting_transcribe(self,meeting_file):
        """
        Trascribe the meeting recording file and stores the output in a S3 bucket
        """
        temp_name_append = uuid.uuid4().hex[:6]

        file_name, file_extension = os.path.splitext(meeting_file)

        job_name = file_name.replace(" ", "_").replace(",","").replace("&","_")
        job_unique_name = f"{job_name}_{temp_name_append}"

        job_uri = f"s3://{self.meeting_recordings_store}/{meeting_file}"

        self.transcribe.start_transcription_job(
            TranscriptionJobName=job_unique_name,
            Media={'MediaFileUri': job_uri},
            MediaFormat=file_extension[1:],
            LanguageCode='en-US',
            OutputBucketName=self.meeting_summary_store,
            OutputKey=f"meetings_summary/{job_unique_name}.json"
        )

        return job_unique_name, job_uri
    
    def get_transcription_status(self, job_name):
        return self.transcribe.get_transcription_job(TranscriptionJobName=job_name)
    
    def get_transcription(self, job_unique_name):
        time.sleep(30)
        response = self.s3.get_object(
            Bucket=self.meeting_summary_store,
            Key=f"meetings_summary/{job_unique_name}.json"
        )
        content = response['Body'].read()

        json_content = json.loads(content)

        transcript = json_content["results"]['transcripts'][0]['transcript']
        items = json_content["results"]['items']

        return transcript, items
        
    def create_claude_body(self, input_text = "some text", token_count = 150, temp = 0.05, topP = 1, topK = 250, stop_sequence = "Human:"):
        body = {
        "prompt": input_text,
            "max_tokens_to_sample": token_count,
            "temperature": temp,
            "top_k": topK,
            "top_p":topP,
            "stop_sequences":[stop_sequence]   
        } 
        return body

    def create_jurassic_body(self, input_text = "some text", token_count = 150, temp = 0.05, topP = 1, stop_sequence = "Human:"):
        body = {
        "prompt": input_text,
            "maxTokens": token_count,
            "temperature": temp,
            "topP":topP,
            "stopSequences":[stop_sequence]   
        } 
        return body

    def create_titan_body(self, input_text = "some text", token_count = 4096, temp = 0.05, topP = 1, stop_sequence = "Human:"):
        body = {
        "inputText": input_text,
            "textGenerationConfig": {
            "maxTokenCount": token_count,
            #   "stopSequences": [stop_sequence],
            "temperature":temp,
            "topP":topP
            }
        } 
        return body

    def get_model_res(self, body, model_id):
            
        resp = self.bedrock.invoke_model(modelId = model_id, body=json.dumps(body), accept = "*/*", contentType = "application/json")
        results = json.loads(resp.get("body").read().decode('utf-8'))
        return results

    def get_bedrock_response(self, prompt, junique_name, meeting_summary_store, token_count = 150, temp = 0, model_id = "anthropic.claude-v2:1"):

        if model_id in ["anthropic.claude-v2:1", "anthropic.claude-v2", "anthropic.claude-instant-v1", "anthropic.claude-v1", "anthropic.claude-v2-100k"]:
            body = self.create_claude_body(input_text = prompt, token_count = token_count, temp = temp, topP = 1, stop_sequence="Human:") # 4096
            results = self.get_model_res(body, model_id)
            response = results['completion']
            self.s3.put_object(Bucket=self.meeting_summary_store, Key=junique_name, Body=response)
        elif model_id in ["ai21.j2-ultra"]:
            body = self.create_jurassic_body(input_text = prompt, token_count = token_count, temp = temp, stop_sequence="Please")
            results = self.get_model_res(body, model_id)
            response = results['completions'][0]['data']['text']
            self.s3.put_object(Bucket=self.meeting_summary_store, Key=junique_name, Body=response)
        else:
            body = self.create_titan_body(input_text = prompt, junique_name = token_count, temp = temp)
            results = self.get_model_res(body, model_id)
            response = results['results'][0]['outputText']
            self.s3.put_object(Bucket=self.meeting_summary_store, Key=junique_name, Body=response)

        return response
        
    def meeting_summarize(self, transcribed_meeting_content, meeting_file):
        """
        Summarize the meeting transcript using Amazon Bedrock
        """
        jname = meeting_file.replace(" ", "_").replace(",","")
        junique_name = f"{jname}_{jname}.txt"

        prompt_template1 = f"""\n\nHuman:
        <meeting transcript>
        {transcribed_meeting_content}
        </meeting transcript>
        
        Please summarize the above meeting transcript 
        \n\nAssistant:"""
        
        prompt_template2 = f"""\n\nHuman:
        <meeting transcript>
        {transcribed_meeting_content}
        </meeting transcript>
        
        Please summarize the above meeting transcript in 3 sentences
        \n\nAssistant:"""
        
        prompt_template3 = f"""\n\nHuman:
        <meeting transcript>
        {transcribed_meeting_content}
        </meeting transcript>
        
        Please summarize the above meeting transcript on a per speaker basis
        \n\nAssistant:"""
        
        prompt_template4 = f"""\n\nHuman:
        <meeting transcript>
        {transcribed_meeting_content}
        </meeting transcript>
        
        Please provide the follow ups each person should take away from the above meeting transcript
        \n\nAssistant:"""

        template_list = [prompt_template1, prompt_template2, prompt_template3, prompt_template4]
        model_list = ["anthropic.claude-v2:1", "ai21.j2-ultra", "anthropic.claude-v2", 
            "anthropic.claude-v2-100k", "anthropic.claude-instant-v1", 
            "amazon.titan-tg1-large", "anthropic.claude-v1"]
        
        prompt_template = prompt_template1 # General summary
        token_count = 150
        
        meeting_summary = self.get_bedrock_response(prompt_template, junique_name, self.meeting_summary_store, token_count = token_count, model_id = model_list[0])
        
        print(meeting_summary)

        return meeting_summary