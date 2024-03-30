from adisconfig import adisconfig
from log import Log
from pika import BlockingConnection, PlainCredentials, ConnectionParameters
from json import loads, dumps
from pprint import pprint
from pathlib import Path
from uuid import uuid4
from os import mkdir
from pymongo import MongoClient
from yuki import prompt
from constants import SYSTEM_MESSAGE, FORMAT_EXAMPLE
from openai import OpenAI

class Director:
    name="yuki-director"

    def __init__(self):
        self._config=adisconfig('/opt/adistools/configs/yuki-director.yaml')

        self._log=Log(
            parent=self,
            rabbitmq_host=self._config.rabbitmq.host,
            rabbitmq_port=self._config.rabbitmq.port,
            rabbitmq_user=self._config.rabbitmq.user,
            rabbitmq_passwd=self._config.rabbitmq.password,
            debug=self._config.log.debug,
            )

        self._prompt=prompt.Prompt()
        self._openai=OpenAI(api_key=self._config.openai.api_key)

        self._rabbitmq_conn = BlockingConnection(
            ConnectionParameters(
                host=self._config.rabbitmq.host,
                port=self._config.rabbitmq.port,
                credentials=PlainCredentials(
                    self._config.rabbitmq.user,
                    self._config.rabbitmq.password
                )
            )
        )

        self._rabbitmq_channel = self._rabbitmq_conn.channel()
        self._rabbitmq_channel.basic_consume(
            queue='yuki-director_requests',
            auto_ack=True,
            on_message_callback=self._director_request
        )


        self._mongo_cli = MongoClient(
            self._config.mongo.host,
            self._config.mongo.port
        )

        self._mongo_db = self._mongo_cli[self._config.mongo.db]
        self._videos_collection=self._mongo_db['videos']

    def _generate_script(self, video_title, video_description, **kwargs):
        completion=self._openai.chat.completions.create(
            model=self._config.openai.model,
            messages=self._prompt.build(
                system_message=SYSTEM_MESSAGE,
                video_title=video_title,
                video_description=video_description,
                format_example=FORMAT_EXAMPLE
                )
        )


        resp=completion.choices[0].message.content
        print(resp)
        return loads(resp)


    def _update_video(self, video_uuid, script):
        query={"video_uuid": video_uuid}

        rep_query={"$set": {'script':script}}

        self._videos_collection.update_one(
            query,
            rep_query
        )


    def _director_request(self, channel, method, properties, body):
        message=loads(body.decode('utf8'))
        pprint(message)

        if message:

            script=self._generate_script(**message)
            self._update_video(
                video_uuid=message['video_uuid'],
                script=script
            )

            message['script']=script

            self._rabbitmq_channel.basic_publish(
                exchange="",
                routing_key="yuki-image_requests",
                body=message['video_uuid']
            )
            self._rabbitmq_channel.basic_publish(
                exchange="",
                routing_key="yuki-speech_requests",
                body=message['video_uuid']
            )



    def start(self):
        self._rabbitmq_channel.start_consuming()

    def stop(self):
        self._rabbitmq_channel.stop_consuming()

if __name__=="__main__":
    director=Director()
    director.start()
