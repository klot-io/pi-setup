pipeline {
    agent any

    stages {
        stage('build api') {
            steps {
                dir('api') {
                    sh 'make build'
                }
            }
        }
        stage('test api') {
            steps {
                dir('api') {
                    sh 'make test'
                }
            }
        }
        stage('lint api') {
            steps {
                dir('api') {
                    sh 'make lint'
                }
            }
        }
        stage('push api') {
            when {
                branch 'master'
            }
            steps {
                dir('api') {
                    sh 'make push'
                }
            }
        }
    }
}
